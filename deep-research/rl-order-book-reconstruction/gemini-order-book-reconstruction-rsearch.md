# **Technical Report: High-Fidelity Order Book Reconstruction and Validation Framework**

## **Executive Summary**

This report presents a comprehensive technical architecture and implementation strategy for the development of a high-performance order book reconstruction pipeline (Epic 2) and an automated fidelity validation framework (Epic 3). The proposed design leverages the exceptional data quality established in Epic 1—specifically, the finding of 0% sequence gaps across 11.15M messages—to build a system capable of meeting the stringent requirements for quantitative backtesting, including a -5bp VWAP performance target.

The recommended architecture is a **Partitioned, Single-Threaded, Event-Sourced State Machine** for each trading instrument. This pattern, adapted from proven high-frequency trading (HFT) systems, is designed to maximize throughput and minimize latency by eliminating lock contention and optimizing CPU cache utilization.<sup>1</sup> State management will be handled transactionally via a pending queue, a robust methodology for processing delta feeds that ensures atomicity and consistency during snapshot initializations and subsequent updates.<sup>2</sup>

To achieve the target throughput of over 100,000 events per second within the Python/Polars ecosystem, this report identifies five critical performance optimizations:

1. **Scaled Integer Arithmetic:** Mitigate the documented performance and stability risks of the Polars Decimal type by representing all prices and sizes as 64-bit integers in the performance-critical hot path.<sup>3</sup>

2. **Micro-Batch Processing:** Group incoming delta messages into small, time-bound batches to enable vectorized, columnar operations, thereby leveraging the core performance strength of Polars' Rust-based engine.<sup>5</sup>

3. **Hybrid Data Structures:** Employ cache-efficient, contiguous arrays for top-of-book levels, where activity is concentrated, and hash maps for deeper, less-frequently accessed levels to optimize update performance.<sup>7</sup>

4. **Asynchronous Copy-on-Write Checkpointing:** Implement a non-blocking state persistence mechanism using a forked-process pattern and memory-mapped files to save the order book state without halting the main event-processing loop.<sup>9</sup>

5. **Proactive Garbage Collection Management:** Control Python's garbage collector by disabling it during batch processing and triggering it manually between batches to eliminate non-deterministic latency spikes.<sup>12</sup>

The fidelity validation framework is designed to prove statistical equivalence between reconstructed and live market data to a degree greater than 99.9%. This is achieved by analyzing a triad of metric categories: (1) **Price and Return Distributions**, confirming heavy-tailed properties via Power Law analysis <sup>13</sup>; (2)

**Temporal Dynamics**, verifying volatility clustering through the autocorrelation of squared returns <sup>14</sup>; and (3)

**Liquidity and Impact Dynamics**, validating the square-root law of price impact and order flow imbalance distributions.<sup>15</sup> The two-sample Kolmogorov-Smirnov test will serve as the primary statistical tool for comparing these distributions.

The principal technical risk identified is the performance and stability of the native Decimal128 type in Polars. The primary mitigation is the adoption of a scaled integer representation for all core logic. A secondary risk, Python's Global Interpreter Lock (GIL), will be mitigated by the proposed multi-process architecture that partitions work by instrument, dedicating a single process per asset to avoid contention. This design ensures the system is both vertically and horizontally scalable, providing a robust foundation for future expansion.


## **1. Order Book Reconstruction Design**

This section details the architectural blueprint for the stateful event replayer. The design prioritizes robustness, performance, and maintainability, drawing from established patterns in low-latency financial systems.


### **1.1 Core Architecture: An Event-Sourced State Machine**

The system will be architected as an **Event-Sourced State Machine**, a pattern where the current state is derived by replaying a sequence of historical events. This approach is naturally suited to order book reconstruction from delta feeds. To achieve high performance and scalability, the architecture will be **partitioned by financial instrument**. Each instrument (e.g., BTC-USDT) will be managed by a dedicated, single-threaded process. This design choice is critical for performance in a Python environment.

High-performance C++ trading systems frequently employ a single thread pinned to a dedicated CPU core to manage an order book, a strategy that eliminates the need for locking mechanisms and their associated overhead, thereby maximizing cache efficiency.<sup>1</sup> However, Python's Global Interpreter Lock (GIL) prevents true multi-threaded parallelism for CPU-bound tasks. Multiple threads within a single Python process would still contend for the GIL, leading to context switching and non-deterministic pauses, which are unacceptable in a low-latency system.<sup>17</sup> Therefore, the single-threaded architectural pattern is elevated to the process level. By assigning each instrument to its own process, we achieve true parallelism at the system level and eliminate contention for the order book state, ensuring that each reconstruction engine operates with maximum efficiency. This design scales by adding more processes for more instruments, a model well-suited to modern multi-core processors.

The architecture comprises four key components:

- **Ingestor/Dispatcher:** A central process responsible for reading the raw delta feed data from storage. It performs initial, lightweight parsing (e.g., deserialization) and dispatches messages for each instrument to the appropriate reconstruction process. Communication will be handled via a high-performance inter-process communication (IPC) mechanism, such as shared memory ring buffers or a message queue like ZeroMQ, to minimize data transfer overhead.

- **Sequencer & Batching Buffer:** Within each reconstruction process, a buffer receives the stream of delta messages for its assigned instrument. This component has two primary responsibilities: ensuring strict sequence integrity by monitoring message sequence numbers, and grouping messages into micro-batches (e.g., by count or time) for efficient downstream processing.<sup>5</sup>

- **Stateful Replayer Engine:** This is the core of the reconstruction process. It consumes micro-batches from the Sequencer and applies the updates to the in-memory order book state. Its logic will be based on the robust transactional update model, which uses a pending queue to handle snapshots and delta updates atomically.<sup>2</sup> This ensures that the book state remains consistent even if snapshots and delta messages overlap, such as during a reconnection or recovery event.

- **State Persistor (Checkpointer):** A component designed to operate asynchronously to persist the order book state to durable storage. It will be triggered at regular intervals (e.g., by message count or time) and will use a non-blocking mechanism to avoid impacting the performance of the Replayer Engine.<sup>10</sup>


### **1.2 State Management and Data Structures**

A monolithic data structure is suboptimal for representing a limit order book due to the highly skewed nature of access patterns; the vast majority of activity occurs at or near the best bid and ask prices. To address this, a **hybrid data structure approach** is recommended.

- **Top-of-Book (Levels 1-20):** This highly active region will be managed using two fixed-size, contiguous NumPy arrays—one for bids and one for asks. Each array will store (price, size) tuples, with price levels mapped directly to array indices for constant-time (O(1)) access. This design is exceptionally cache-friendly, enabling rapid updates near the spread and immediate retrieval of the best bid and ask.<sup>7</sup> To facilitate efficient modifications and cancellations, which are identified by a unique\
  order\_id, a separate hash map (dict) will be maintained to map order\_id to its corresponding details, including price and size. This allows for quick lookups without traversing the price-level structures.<sup>1</sup>

- **Deep Book (Levels 21+):** The less frequently accessed, deeper parts of the book will be managed using Python's native dict for both bids and asks, with price levels as keys and aggregated volume as values. This provides an average time complexity of O(1) for price-level lookups. While dictionaries are not inherently sorted, the keys can be extracted and sorted on the rare occasions when a full, deep view of the book is required for analysis. This approach pragmatically avoids the computational overhead of maintaining a self-balancing binary search tree (a concern noted for its complexity even in hardware implementations <sup>20</sup>) for levels where update frequency is low.

The representation of an individual order will be a memory-efficient object, such as a namedtuple or a class with \_\_slots\_\_, containing order\_id, price, size, and timestamp. This minimizes the overhead associated with object creation and storage.

The core update logic within the Replayer Engine will follow these steps:

- **Add/Update Order:**

1. Receive a delta message, for example: {type: 'UPDATE', order\_id: 123, price: 30000.50, size: 0.5, side: 'BID'}.

2. Check the order\_id -> details map for the existence of order\_id: 123.

3. If it exists (an update), retrieve the old price and size. Decrement the volume at the old price level in the appropriate data structure (top-of-book array or deep book dict).

4. Increment the volume at the new price level.

5. Update the order\_id -> details map with the new information.

- **Cancel Order:**

1. Receive a delta message, for example: {type: 'CANCEL', order\_id: 123}.

2. Look up order\_id: 123 in the map to retrieve its price and size.

3. Decrement the volume at the corresponding price level.

4. Delete the entry for order\_id: 123 from the map.


### **1.3 Efficient Book State Checkpointing and Recovery**

To ensure fault tolerance without compromising performance, an **asynchronous, copy-on-write (CoW) checkpointing** strategy is essential. This mechanism allows the system to save its state to durable storage without pausing the critical event processing loop.<sup>10</sup>

The checkpointing process will be triggered based on configurable parameters, such as every one million messages processed or every 60 seconds. The procedure is as follows:

1. The main replayer process initiates a checkpoint and forks a child process. Due to the copy-on-write semantics of modern operating systems, this fork() operation is nearly instantaneous and highly memory-efficient, as it does not immediately duplicate the parent's memory space.<sup>10</sup>

2. The parent (replayer) process continues its work, processing new incoming delta messages without interruption.

3. The child process inherits a static, point-in-time snapshot of the parent's memory, including the complete order book state. This child process is then responsible for the slow I/O operation: it serializes the order book data structures (e.g., using a high-performance library like msgpack or a custom binary format) and writes the state to a memory-mapped file.<sup>22</sup> This effectively isolates the I/O-bound task from the CPU-bound hot path.

Recovery from a shutdown or failure is straightforward and robust:

1. Upon startup, the replayer process locates the most recent valid checkpoint file.

2. It loads the serialized order book state from this file directly into its memory space, rapidly re-establishing the last known good state.

3. It then queries the delta feed source, requesting the message stream starting from the sequence number immediately following the one recorded in the checkpoint.

4. The replayer begins consuming and applying these deltas to bring the book state up to the present moment. This combined approach of snapshot loading and subsequent event replay is a standard and highly reliable recovery pattern in event-sourced systems.<sup>23</sup>


### **1.4 Handling Edge Cases**

While Epic 1 demonstrated perfect data quality in the sample, a production-grade system must be architected for resilience against potential future data degradation.

- **Sequence Gap Detection:** The Sequencer component will maintain the expected next sequence number. If an incoming message has a number greater than expected, a gap is detected, and a recovery protocol is initiated.

- **Gap Recovery Protocol:**

1. **Halt Processing:** The replayer engine immediately stops applying new delta messages to prevent state corruption.

2. **Request Snapshot:** The system programmatically requests a full order book snapshot from the data source.

3. **State Reset:** Upon receiving a message with the SNAPSHOT\_BEGIN flag, the current in-memory order book is completely discarded.<sup>2</sup>

4. **Snapshot Rebuild:** The incoming stream of snapshot messages is used to construct a new, guaranteed-consistent order book state.

5. **Resume Processing:** After the SNAPSHOT\_END flag is received, the system resumes applying live delta messages. Any messages that arrived during the snapshot rebuild are buffered and replayed in the correct sequence to ensure no events are lost.

- **Out-of-Order Updates:** To handle minor message reordering caused by network latency, the Sequencer will maintain a small look-ahead buffer (e.g., capable of holding 100-1000 messages). Messages within this buffer can be sorted by sequence number before being released to the replayer. If a message arrives that is too far out of order to be corrected by the buffer, it will be treated as a sequence gap, triggering the full recovery protocol described above.


## **2. Performance Optimization Strategies**

This section details specific, actionable techniques to achieve the required 100k+ events/second throughput within the Python/Polars environment, focusing on bridging the gap between the iterative nature of order book updates and the vectorized strengths of modern data-processing libraries.


### **2.1 Micro-Batching and Vectorized Operations in Polars**

The primary performance challenge lies in reconciling the inherently serial, row-by-row nature of applying single delta updates with the high-performance, vectorized paradigm of Polars.<sup>6</sup> Direct iteration over Polars DataFrames or applying single updates in a loop is notoriously slow and would fail to meet the performance target.

The solution is **micro-batching**. The Sequencer component will group incoming messages into small batches, defined either by a message count (e.g., 100-1000 messages) or a time interval (e.g., 10 milliseconds). This batch of updates can then be represented as a Polars DataFrame and applied to the order book state using efficient, single-shot columnar operations. This approach is not merely an I/O optimization; it is the fundamental enabler for leveraging Polars' core performance advantage. It transforms a high-frequency stream of scalar operations into a series of highly efficient, vectorized operations, amortizing the overhead of the Python-to-Rust interface and allowing the underlying SIMD-optimized engine to operate on entire columns of data at once.<sup>25</sup>

The optimal batch size is a critical tuning parameter representing a trade-off between throughput and latency.<sup>5</sup> A larger batch size increases throughput by making each columnar operation more efficient, but it also increases the latency for the first message in the batch. Conversely, a smaller batch size reduces latency but may decrease overall throughput due to higher per-batch overhead. This parameter must be determined empirically through rigorous benchmarking on the target hardware.


### **2.2 Minimizing Memory Allocation and GC Overhead**

In a high-throughput Python application, the continuous creation and destruction of objects can lead to significant and unpredictable pauses for garbage collection (GC), introducing unacceptable latency jitter.<sup>12</sup> Several strategies will be employed to mitigate this.

- **Object Pooling:** A pool of Order objects will be pre-allocated at startup. When a new order arrives, an object is taken from this pool and populated with data, rather than instantiating a new one. When an order is canceled or filled, its object is returned to the pool for reuse. This dramatically reduces the rate of object allocation and deallocation.

- **Memory-Efficient Objects:** The Order class will be defined using \_\_slots\_\_ to prevent the creation of a \_\_dict\_\_ for each instance, significantly reducing the memory footprint of each object and improving attribute access speed.

- **Manual GC Control:** To make GC behavior deterministic, the core batch processing loop will be wrapped with gc.disable() before execution and gc.enable() after. A manual gc.collect() will be triggered strategically between batches or during brief idle periods. This ensures that GC pauses do not occur unpredictably in the middle of a performance-sensitive operation.<sup>12</sup>

- **Zero-Copy Operations:** Where possible, Polars' lazy execution engine will be used for any analytical computations on the book state. This allows for chaining operations without creating unnecessary intermediate copies of DataFrames in memory, conserving memory and reducing GC pressure.<sup>25</sup>


### **2.3 Decimal128 Performance Optimization and Risk Mitigation**

A significant technical risk to the project is the reliance on Polars' Decimal type. The official documentation marks this feature as "unstable" and subject to change without notice.<sup>3</sup> Community discussions and issue trackers reveal a history of regressions and ongoing debates about its implementation, performance, and API design.<sup>4</sup> While floating-point arithmetic is unsuitable for financial calculations due to precision errors <sup>31</sup>, using an unstable

Decimal type in the performance-critical hot path is equally untenable.

The primary mitigation strategy is to **avoid the Decimal type entirely within the reconstruction engine's hot path by using scaled integers**.

1. **Establish Precision:** A system-wide precision standard for prices and sizes will be defined (e.g., 8 decimal places, sufficient for most crypto assets).

2. **Integer Representation:** All price and size values will be converted to 64-bit integers (Int64) upon ingestion by multiplying them by a scaling factor (e.g., 108). For instance, a price of 30000.12345678 becomes the integer 3000012345678.

3. **Hot-Path Computation:** All state updates, comparisons, and arithmetic within the replayer engine will be performed on these native integers. These operations are executed with maximum efficiency by the CPU and are highly optimized within Polars.

4. **Boundary Conversion:** The scaled integers will be converted back to a high-precision Decimal representation only at the system's boundaries—when data is being checkpointed to disk or served via an API for downstream analysis. This strategy confines the use of the potentially slower and less stable Decimal type to non-performance-critical paths, ensuring the core engine remains fast, stable, and precise.


### **2.4 Leveraging Polars' Query Optimizer**

While the reconstruction process itself is a stateful, iterative operation, any subsequent analytical queries performed on the generated order book snapshots must leverage Polars' lazy API and query optimizer. For example, when calculating features or microstructure metrics from checkpointed data, operations should be constructed as a lazy query plan. This allows Polars' optimizer to apply crucial performance enhancements like **Predicate Pushdown** and **Projection Pushdown**.<sup>27</sup> If a query requires calculating the VWAP for a specific 5-minute window, the optimizer will ensure that only the rows within that time range and only the necessary

price and volume columns are ever loaded from the disk file. This drastically reduces I/O and memory consumption compared to eagerly loading the entire dataset and then filtering it.


## **3. Fidelity Validation Framework**

This section specifies a rigorous, multi-faceted framework to statistically validate that the reconstructed order book is a high-fidelity representation of the real market. The goal is to move beyond simple price matching and prove that the subtle, dynamic properties of the market have been preserved, which is essential for building a reliable backtesting environment.


### **3.1 A Suite of Market Microstructure Metrics**

A single metric is insufficient to capture the complex behavior of a limit order book. Fidelity must be assessed across multiple dimensions of market dynamics, including liquidity, return distributions, temporal patterns, and order flow. This suite of metrics is designed to capture the well-documented "stylized facts" of financial time series, ensuring the reconstructed data is not just superficially correct but structurally and dynamically equivalent to the source.<sup>32</sup>

The following table outlines the core metrics that will form the basis of the validation framework.

|                        |                              |                                                  |                                                                                                           |                                                                                                       |                                                                                                |
| ---------------------- | ---------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Metric Category        | Metric Name                  | Mathematical Definition                          | Significance & What It Measures                                                                           | Expected Property                                                                                     | Relevant Snippets                                                                              |
| **Liquidity & Spread** | Time-Weighted Avg. Spread    | T1​∫0T​(Ask1​(t)−Bid1​(t))dt                     | The average transaction cost and market tightness. A fundamental measure of liquidity.                    | Match golden sample within a tight tolerance (e.g., < 0.1%).                                          | <sup>32</sup>                                                                                  |
|                        | Order Book Depth             | ∑i=1N​Volume(pi​) for top N levels               | The market's capacity to absorb large orders without significant price movement.                          | The empirical distribution of depths should match the golden sample.                                  | <sup>32</sup>                                                                                  |
|                        | Price Impact (Kyle's Lambda) | λ from regression Δp=λ⋅(TradeDirection⋅Volume)+ϵ | The market's price sensitivity to signed order flow. Measures permanent impact.                           | Estimated λ from reconstructed data should be statistically identical to that from the golden sample. | <sup>15</sup>                                                                                  |
| **Return Dynamics**    | Return Distribution Kurtosis | σ4E​                                             | Measures the "fat tails" of the return distribution, indicating the frequency of extreme events.          | High kurtosis (>3), matching the golden sample's value.                                               | <sup>13</sup>                                                                                  |
|                        | Power Law of Returns         | $P(                                              | R                                                                                                         | > x) \sim x^{-\alpha}$                                                                                | Confirms the heavy-tailed nature of large price movements, a key feature of financial markets. |
| **Temporal Dynamics**  | Volatility Clustering        | Corr(Rt2​,Rt−τ2​) for τ>0                        | The tendency for large price changes to be followed by large changes, and small by small.                 | A positive and slowly decaying autocorrelation function for squared returns.                          | <sup>14</sup>                                                                                  |
|                        | Order Arrival Rate           | Events per second                                | Measures the intensity of market activity. Can be modeled with a self-exciting Hawkes process.            | The distribution of arrival rates (e.g., per minute) should match the golden sample.                  | <sup>67</sup>                                                                                  |
| **Order Flow**         | Order Flow Imbalance (OFI)   | ΔVbid,1​−ΔVask,1​                                | A powerful short-term predictor of price movements based on net liquidity changes at the top of the book. | The empirical distribution of OFI values should match the golden sample.                              | <sup>16</sup>                                                                                  |


### **3.2 Efficient Online Computation of Metrics**

To enable continuous validation and avoid costly recalculations over the entire historical dataset, these metrics will be computed using efficient online or streaming algorithms.

- **Rolling Statistics:** For metrics like time-weighted average spread and order book depth, Polars' highly optimized rolling window functions can be used to compute statistics over a sliding time window. For metrics that require a longer lookback, exponential moving averages (EMAs) provide a computationally cheap alternative.

- **Volatility Modeling:** Volatility clustering is best captured by GARCH models. A GARCH(1,1) model can be fitted to the return series to estimate conditional volatility. The Python arch package provides an efficient implementation suitable for this purpose.<sup>35</sup>

- **Power Law Estimation:** Accurately estimating the tail index α requires specialized techniques. The powerlaw Python package implements statistically sound methods for fitting heavy-tailed distributions, including finding the optimal lower bound (xmin​) for the power-law tail, which is crucial for avoiding biased estimates.<sup>37</sup> This analysis can be performed on daily or weekly batches of return data.


### **3.3 Statistical Tests for Definitive Validation**

Visual inspection and simple comparisons are insufficient for rigorous validation. Statistical hypothesis testing is required to provide a definitive, quantitative assessment of fidelity.

The primary tool for this will be the **two-sample Kolmogorov-Smirnov (K-S) test**. This test is ideal for the task because it is non-parametric, meaning it makes no assumptions about the underlying distribution of the data (e.g., normality). This is critical, as financial data is well-known to be non-normal, exhibiting properties like skewness and heavy tails.<sup>39</sup> The K-S test directly compares the empirical cumulative distribution functions (ECDFs) of two samples to determine if they are drawn from the same distribution.<sup>41</sup>

The validation process for each metric's distribution will follow a formal hypothesis testing framework:

- **Null Hypothesis (H0​):** The distribution of the metric (e.g., 1-second returns) from the reconstructed data is identical to the distribution from the golden sample data.

- **Alternative Hypothesis (Ha​):** The two distributions are different.

- **Test Execution:** The scipy.stats.ks\_2samp function will be used to perform the test, yielding a test statistic (D) and a p-value.

- **Interpretation:** The p-value represents the probability of observing a difference as large as the one measured if the null hypothesis were true. A high p-value (e.g., > 0.05) indicates that there is no statistical evidence to reject the null hypothesis. This provides strong support for the conclusion that the reconstructed data faithfully reproduces the distributional properties of the real market for that specific metric. Conversely, a low p-value signals a statistically significant discrepancy, flagging a potential fidelity issue that must be investigated.


### **3.4 Automated Pass/Fail Criteria and Visualization**

To create a fully automated validation framework (Epic 3), the results of the statistical tests must be translated into objective, machine-readable pass/fail criteria. This forms the core of the quality assurance gate in a continuous integration pipeline.

|                                         |                             |                      |                                                                                                                             |                   |
| --------------------------------------- | --------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| Metric                                  | Statistical Test            | Threshold for "Pass" | Rationale                                                                                                                   | Relevant Snippets |
| 1-sec Returns Distribution              | Two-Sample K-S Test         | p-value > 0.05       | Ensures the fundamental distribution of price changes, including its central moments and tails, is statistically identical. | <sup>39</sup>     |
| Order Flow Imbalance (OFI) Distribution | Two-Sample K-S Test         | p-value > 0.05       | Validates the integrity of a key short-term predictive signal, crucial for RL agent training.                               | <sup>16</sup>     |
| Power Law Exponent α                    | Relative Difference         | < 1%                 | Confirms that the model correctly captures the probability of extreme events, which is critical for risk management.        | <sup>44</sup>     |
| Autocorrelation (Lag 1) of R2           | Relative Difference         | < 5%                 | Validates that the magnitude and presence of volatility clustering, a key temporal property, are preserved.                 | <sup>14</sup>     |
| Price Impact λ                          | Confidence Interval Overlap | Overlap > 80%        | Ensures the reconstructed market exhibits the same liquidity dynamics and response to trading activity.                     | <sup>15</sup>     |

To complement the quantitative tests, a suite of visualizations will be generated for human oversight and in-depth analysis:

- **Log-Log Plots:** These are essential for visualizing the tails of distributions like returns or trade sizes. A straight line on a log-log plot is the classic signature of a power law, providing clear visual confirmation of heavy-tailed behavior.<sup>38</sup>

- **Quantile-Quantile (Q-Q) Plots:** These plots compare the quantiles of the reconstructed data distribution against the golden sample distribution. A perfect match will result in points lying along the y=x line, while deviations from this line highlight specific parts of the distribution (e.g., tails, center) where fidelity may be weak.

- **Autocorrelation Function (ACF) Plots:** These are used to visualize the decay of autocorrelation for squared returns. The characteristic slow decay of the ACF is the hallmark of volatility clustering and must be present in the reconstructed data.<sup>45</sup>

- **Fidelity Dashboards:** A web-based dashboard (e.g., using Plotly Dash or Grafana) will be created to display the key fidelity metrics, their historical trends, and their current pass/fail status. This provides an at-a-glance view of system health for all stakeholders.<sup>46</sup>


## **4. Implementation Roadmap and Advanced Features**

This section outlines a phased implementation plan, details advanced features to be derived from the reconstructed book for downstream RL training, and describes the architecture for scaling the system and automating quality assurance.


### **4.1 Prioritized Implementation Roadmap**

A phased approach will be adopted to manage complexity and deliver value incrementally.

- **Phase 1 (Epic 2 Start): Core Reconstruction Engine**

* **Objective:** Build a functional, single-instrument reconstruction pipeline.

* **Tasks:**

- Implement the core Stateful Replayer Engine using the hybrid data structure (NumPy arrays for top-of-book, dict for deep book).

- Implement the transactional update logic based on the pending queue model.<sup>2</sup>

- Establish the scaled integer representation for all internal price and size calculations as a foundational decision.

- Develop basic fidelity checks, such as bit-for-bit L1 price and volume matching against a small, known-good golden sample.

* **Phase 2 (Epic 2 Mid-point): Performance and Persistence**

- **Objective:** Achieve the performance target and ensure fault tolerance.

- **Tasks:**

* Implement micro-batching in the Sequencer and refactor the Replayer to use vectorized Polars operations. Benchmark and tune the optimal batch size.

* Implement proactive memory management, including object pooling and manual GC control.

* Develop and integrate the asynchronous, copy-on-write checkpointing mechanism and the corresponding recovery logic.

* Implement the complete suite of market microstructure metrics and statistical tests defined in Section 3.

- **Phase 3 (Epic 3 Start): Automation and Scaling**

* **Objective:** Build the automated validation framework and scale the system for multi-asset processing.

* **Tasks:**

- Build the CI/CD pipeline that automatically executes the full fidelity suite on every code change, acting as a quality gate.

- Develop the fidelity dashboard for visualization and reporting.

- Refactor the single-process application into the multi-process, partitioned architecture using an IPC message bus to handle multiple instruments concurrently.


### **4.2 Advanced Derived Features for RL Training**

The raw, high-dimensional state of the limit order book is often a suboptimal input for reinforcement learning agents. A set of well-engineered, lower-dimensional features can provide a more informative and stable state representation, accelerating learning and improving final performance.<sup>47</sup> The following features will be calculated from the reconstructed book state at each time step:

- **Order Flow Imbalance (OFI):** As defined previously, OFI measures the net change in liquidity at the best bid and ask. It has been shown to have significant predictive power for short-term price movements and is a critical input for any liquidity-taking agent.<sup>16</sup>

- **Book Pressure:** This feature captures the weighted volume on both sides of the book. A common formulation is a ratio or difference of weighted sums, e.g., BookPressure=∑i=1N​wi​⋅(Vbid,i​+Vask,i​)∑i=1N​wi​⋅Vbid,i​−∑i=1N​wi​⋅Vask,i​​, where weights wi​ decrease for levels further from the mid-price. This provides a snapshot of the overall market sentiment embedded in the resting orders.

- **Queue Position:** For a hypothetical limit order placed by the RL agent, this feature estimates its position in the queue at a given price level. It can be calculated as the ratio of volume in front of the agent's order to the total volume at that level. This is essential for the agent to learn the trade-off between price improvement and probability of execution.<sup>47</sup>

- **Market Impact Forecast:** A simple, real-time market impact model will be implemented as a feature. For example, using the square-root law, the agent can be provided with an estimate of the price impact for a potential trade of size Q: ΔP≈λQ​, where λ is the empirically measured impact parameter. This allows the agent to learn to manage its execution costs proactively.<sup>15</sup>


### **4.3 Scalability and Quality Assurance Automation**

- **Multi-Asset Distributed Architecture:**

* **Pattern:** To scale beyond a single machine and handle numerous assets, a distributed publish-subscribe architecture will be employed. The central Ingestor process will publish delta messages for different instruments to distinct topics on a high-throughput message bus like Apache Kafka or Redis Pub/Sub.<sup>1</sup>

* **Scaling:** Each instrument's reconstruction engine will run as an independent consumer service, for example, as a container within a Kubernetes pod. This cloud-native approach allows the system to scale horizontally and elastically; adding support for a new instrument is as simple as deploying a new consumer pod.<sup>53</sup> This architecture also provides inherent resilience, as the failure of one pod does not affect the others.

- **Continuous Integration/Continuous Delivery (CI/CD) for Fidelity:**

* **Trigger:** The CI/CD pipeline will be triggered on every code commit to the project's version control repository.

* **Pipeline Stages:**

1. **Static Analysis & Unit Tests:** Standard code quality checks and unit tests are run to catch basic errors.

2. **Integration Test:** The full reconstruction pipeline is deployed in a test environment and run on a small, standardized "golden" dataset (e.g., one hour of high-activity market data).

3. **Fidelity Validation:** The automated fidelity validation framework (from Epic 3) is executed on the output of the integration test. It computes all microstructure metrics and performs the statistical comparisons against the known-good metrics from the golden dataset.

4. **Report Generation:** A comprehensive fidelity report is generated, detailing the results of each test and providing a clear pass/fail status based on the predefined thresholds from Section 3.4.

5. **Deployment Gate:** The pipeline is configured such that the new code version can only be promoted to staging or production environments if 100% of the automated fidelity tests pass. This ensures that no code change that degrades the quality of the reconstructed data can ever reach production.<sup>54</sup>

- **Monitoring and Alerting:**

* The production system will be instrumented with comprehensive monitoring to track key performance indicators (KPIs) such as message throughput, processing latency per batch, memory utilization, and CPU load for each reconstruction process.

* Alerts will be configured to detect anomalies in real-time, such as a sudden drop in throughput, a spike in latency, or the appearance of sequence gaps in the live feed. This allows for early detection and mitigation of operational issues or degradation in data provider quality.<sup>54</sup>


#### **Works cited**

1. Building a Stock Trading System: High-Frequency Trading ..., accessed on July 21, 2025, <https://dev.to/sgchris/building-a-stock-trading-system-high-frequency-trading-architecture-e2f>

2. Order Book Reconstruction - dxFeed KB, accessed on July 21, 2025, <https://kb.dxfeed.com/en/data-model/market-events/dxfeed-order-book/order-book-reconstruction.html>

3. polars.datatypes.Decimal — Polars documentation, accessed on July 21, 2025, <https://docs.pola.rs/api/python/stable/reference/api/polars.datatypes.Decimal.html>

4. Int128 / Decimal128 design discussion · Issue #7178 · pola-rs/polars - GitHub, accessed on July 21, 2025, <https://github.com/pola-rs/polars/issues/7178>

5. How does batching multiple queries together affect latency and throughput? In what scenarios is batch querying beneficial or detrimental for vector search? - Milvus, accessed on July 21, 2025, <https://milvus.io/ai-quick-reference/how-does-batching-multiple-queries-together-affect-latency-and-throughput-in-what-scenarios-is-batch-querying-beneficial-or-detrimental-for-vector-search>

6. The Polars Revolution: A Faster Alternative to Pandas? | by Tanishq Rawat - Medium, accessed on July 21, 2025, <https://medium.com/simform-engineering/the-polars-revolution-a-faster-alternative-to-pandas-db1572c89285>

7. How to write fast orderbook in rust? HFT - Reddit, accessed on July 21, 2025, <https://www.reddit.com/r/rust/comments/1cknjhj/how_to_write_fast_orderbook_in_rust_hft/>

8. Efficient structure for order book operations in python : r/algotrading - Reddit, accessed on July 21, 2025, <https://www.reddit.com/r/algotrading/comments/cnl3ir/efficient_structure_for_order_book_operations_in/>

9. On Checkpoint Latency - Nitin Vaidya, accessed on July 21, 2025, <http://disc.ece.illinois.edu/publications/fault-tolerance/prfts95latency.pdf>

10. Asynchronous checkpoints, accessed on July 21, 2025, <https://www.cs.cmu.edu/afs/cs/user/jl/www-old/CMU-CS-93-124/subsection3_4_4.html>

11. Copy-On-Write - When to Use It, When to Avoid It - Arpit Bhayani, accessed on July 21, 2025, <https://arpitbhayani.me/blogs/copy-on-write/>

12. Understanding Python's Garbage Collection and Memory ..., accessed on July 21, 2025, <https://dev.to/pragativerma18/understanding-pythons-garbage-collection-and-memory-optimization-4mi2>

13. Heavy-tailed distribution - Wikipedia, accessed on July 21, 2025, <https://en.wikipedia.org/wiki/Heavy-tailed_distribution>

14. Volatility clustering - Wikipedia, accessed on July 21, 2025, <https://en.wikipedia.org/wiki/Volatility_clustering>

15. Four must-read market microstructure papers you might have ..., accessed on July 21, 2025, <https://www.globaltrading.net/four-must-read-market-microstructure-papers-you-might-have-missed/>

16. Key insights: Imbalance in the order book - Open Source Quant, accessed on July 21, 2025, <https://osquant.com/papers/key-insights-limit-order-book/>

17. 11 Best Practices for Low Latency Systems | by Ben Darfler - Medium, accessed on July 21, 2025, <https://bdarfler.medium.com/11-best-practices-for-low-latency-systems-a00fc6e0dfda>

18. Batching and Low Latency - Vanilla Java, accessed on July 21, 2025, <https://vanilla-java.github.io/2016/07/09/Batching-and-Low-Latency.html>

19. Checkpointing Strategies for Database Systems - Number Analytics, accessed on July 21, 2025, <https://www.numberanalytics.com/blog/checkpointing-strategies-for-database-systems>

20. HFT Accelerator - MIT, accessed on July 21, 2025, <https://web.mit.edu/6.111/volume2/www/f2019/projects/endrias_Project_Proposal_Revision.pdf>

21. The Power of Snapshots: Exploring Copy-On-Write in SQL Server, accessed on July 21, 2025, <https://www.sqltabletalk.com/?p=234>

22. Python mmap: Improved File I/O With Memory Mapping, accessed on July 21, 2025, <https://realpython.com/python-mmap/>

23. 4\. Stateful Processing - Mastering Kafka Streams and ksqlDB \[Book] - O'Reilly Media, accessed on July 21, 2025, <https://www.oreilly.com/library/view/mastering-kafka-streams/9781492062486/ch04.html>

24. Order Flow Reconstruction | QuestDB, accessed on July 21, 2025, <https://questdb.com/glossary/order-flow-reconstruction/>

25. Level Up Your Data Analysis with Polars: A Powerful DataFrame Library for Speed and Efficiency | by Ravi - Python in Plain English, accessed on July 21, 2025, <https://python.plainenglish.io/level-up-your-data-analysis-with-polars-a-powerful-dataframe-library-for-speed-and-efficiency-0b82c226c7f1>

26. Memory Management in Apache Flink: Techniques for Efficient State Handling - IJIRMPS, accessed on July 21, 2025, <https://www.ijirmps.org/papers/2023/6/231999.pdf>

27. Optimizations - Polars user guide, accessed on July 21, 2025, <https://docs.pola.rs/user-guide/lazy/optimizations/>

28. polars.datatypes.Decimal — Polars documentation, accessed on July 21, 2025, <https://docs.pola.rs/docs/python/dev/reference/api/polars.datatypes.Decimal.html>

29. polars' ingestion of decimal.Decimal values fails if all values do not have the same number of decimal places · Issue #17770 · pola-rs/polars - GitHub, accessed on July 21, 2025, <https://github.com/pola-rs/polars/issues/17770>

30. Support for Decimal series? · Issue #4104 · pola-rs/polars - GitHub, accessed on July 21, 2025, <https://github.com/pola-rs/polars/issues/4104>

31. High performance, high precision, zero allocation decimal library : r/golang - Reddit, accessed on July 21, 2025, <https://www.reddit.com/r/golang/comments/1g3gxn2/high_performance_high_precision_zero_allocation/>

32. Mastering Market Microstructure for Success - Number Analytics, accessed on July 21, 2025, <https://www.numberanalytics.com/blog/mastering-market-microstructure-financial-institutions>

33. 5 Top Pro Tips for Microstructure in Finance - Number Analytics, accessed on July 21, 2025, <https://www.numberanalytics.com/blog/5-top-pro-tips-microstructure-finance>

34. arXiv: Trading and Market Microstructure | 726 Publications | 3522 Citations | Top authors | Related journals - SciSpace, accessed on July 21, 2025, <https://scispace.com/journals/arxiv-trading-and-market-microstructure-3sulqbr7>

35. campus.datacamp.com, accessed on July 21, 2025, <https://campus.datacamp.com/courses/garch-models-in-python/garch-model-fundamentals?ex=9#:~:text=We%20can%20implement%20GARCH%20models,use%20to%20define%20GARCH%20models.>

36. How to implement GARCH models in Python, accessed on July 21, 2025, <https://campus.datacamp.com/courses/garch-models-in-python/garch-model-fundamentals?ex=9>

37. powerlaw: A Python Package for Analysis of Heavy-Tailed Distributions - PubMed Central, accessed on July 21, 2025, <https://pmc.ncbi.nlm.nih.gov/articles/PMC3906378/>

38. powerlaw: A Python Package for Analysis of Heavy-Tailed Distributions | PLOS One, accessed on July 21, 2025, <https://journals.plos.org/plosone/article/figures?id=10.1371/journal.pone.0085777>

39. Kolmogorov-Smirnov Test | SightX, accessed on July 21, 2025, <https://sightx.io/glossary/kolmogorov-smirnov-test>

40. Kolmogorov-Smirnov Test \[KS Test]: When and Where to Use - Dataaspirant, accessed on July 21, 2025, <https://dataaspirant.com/kolmogorov-smirnov-test/>

41. Practical Insights: Applying Kolmogorov-Smirnov Test in Data Analysis - Number Analytics, accessed on July 21, 2025, <https://www.numberanalytics.com/blog/practical-insights-kolmogorov-smirnov-data-analysis>

42. Kolmogorov-Smirnov Test (KS Test) - GeeksforGeeks, accessed on July 21, 2025, <https://www.geeksforgeeks.org/machine-learning/kolmogorov-smirnov-test-ks-test/>

43. ks\_2samp — SciPy v1.16.0 Manual, accessed on July 21, 2025, <https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ks_2samp.html>

44. Power Laws in Economics and Finance - NYU Stern, accessed on July 21, 2025, <https://pages.stern.nyu.edu/~xgabaix/papers/pl-ar.pdf>

45. Volatility Clustering: Auto-correlations of squared returns | Download Table - ResearchGate, accessed on July 21, 2025, <https://www.researchgate.net/figure/Volatility-Clustering-Auto-correlations-of-squared-returns_tbl2_228232175>

46. 3 tips for setting up your charts - Fidelity Investments, accessed on July 21, 2025, <https://www.fidelity.com/viewpoints/active-investor/how-to-set-up-your-charts>

47. Reinforcement learning in a dynamic limit order market - NYU Stern, accessed on July 21, 2025, <https://pages.stern.nyu.edu/~jhasbrou/SternMicroMtg/SternMicroMtg2025/Program%20Papers%20SMC%202025/reinforcement%20learning%20kwan%20philip%2028.pdf>

48. Asynchronous Deep Double Dueling Q-learning for ... - Frontiers, accessed on July 21, 2025, <https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2023.1151003/full>

49. Feature Engineering in Trading: Turning Data into Insights - LuxAlgo, accessed on July 21, 2025, <https://www.luxalgo.com/blog/feature-engineering-in-trading-turning-data-into-insights/>

50. Online feature engineering for high-frequency trading limit order books - YouTube, accessed on July 21, 2025, <https://www.youtube.com/watch?v=w_UPQ3xBDhg>

51. Machine Learning for Statistical Arbitrage II: Feature Engineering and Model Development, accessed on July 21, 2025, <https://www.mathworks.com/help/finance/machine-learning-for-statistical-arbitrage-ii-feature-engineering-model-development.html>

52. Limit Order Book Dataset Generation for Accelerated Short-Term Price Prediction with RAPIDS - NVIDIA, accessed on July 21, 2025, <https://resources.nvidia.com/en-us-financial-services-industry/limit-order-book-data>

53. (PDF) Architecting Distributed Systems for Real-Time Data ..., accessed on July 21, 2025, <https://www.researchgate.net/publication/387903009_Architecting_Distributed_Systems_for_Real-Time_Data_Processing_in_Multi-Cloud_Environments>

54. What is CI/CD for Data? - Dremio, accessed on July 21, 2025, <https://www.dremio.com/wiki/ci-cd-for-data/>

55. What is a CI/CD Pipeline? Benefits & Best Practices - Snowflake, accessed on July 21, 2025, <https://www.snowflake.com/en/fundamentals/understanding-ci-cd-pipelines/>

56. How CI/CD Is Different for Data Science · Andrew Goss · Data Eng ..., accessed on July 21, 2025, <https://andrewrgoss.com/2023/how-ci/cd-is-different-for-data-science/>

57. Data Validation Automation: A Key to Efficient Data Management - Functionize, accessed on July 21, 2025, <https://www.functionize.com/ai-agents-automation/data-validation>

58. Automating large-scale data quality verification - Amazon Science, accessed on July 21, 2025, <https://www.amazon.science/publications/automating-large-scale-data-quality-verification>

59. Automate Finance Data Validation for Accuracy & Efficiency - Datagrid, accessed on July 21, 2025, <https://www.datagrid.com/blog/automate-finance-data-validation>

60. Data Quality Automation: Benefits, Tools & Use Cases - DQLabs, accessed on July 21, 2025, <https://www.dqlabs.ai/blog/data-quality-automation/>

61. Measuring Liquidity in Finiancial Markets - WP/02/232 - International ..., accessed on July 21, 2025, <https://www.imf.org/external/pubs/ft/wp/2002/wp02232.pdf>

62. Understanding Liquidity and How to Measure It - Investopedia, accessed on July 21, 2025, <https://www.investopedia.com/terms/l/liquidity.asp>

63. Order Flow Analysis: A Complete Guide to Reading Market Dynamics Like a Pro, accessed on July 21, 2025, <https://tradefundrr.com/order-flow-analysis/>

64. Order Flow Imbalance Models - QuestDB, accessed on July 21, 2025, <https://questdb.com/glossary/order-flow-imbalance-models/>

65. 22\. Heavy-Tailed Distributions - A First Course in Quantitative Economics with Python, accessed on July 21, 2025, <https://intro.quantecon.org/heavy_tails.html>

66. Power Laws in Economics: An Introduction - Harvard DASH, accessed on July 21, 2025, <https://dash.harvard.edu/bitstreams/7312037e-6eb1-6bd4-e053-0100007fdf3b/download>

67. Reconstructing the Order Book - CiteSeerX, accessed on July 21, 2025, <https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=d7d14288de33bfc153bcbe8f52f05535f36b2d37>

68. osquant.com, accessed on July 21, 2025, <https://osquant.com/papers/key-insights-limit-order-book/#:~:text=The%20net%20order%20flow%20imbalance,as%20the%20direction%20of%20volume.>

69. MSA Explained: 2023 Guide - Capvidia, accessed on July 21, 2025, <https://www.capvidia.com/blog/msa-guide>

70. (PDF) Fidelity Metrics for Estimation Models - ResearchGate, accessed on July 21, 2025, <https://www.researchgate.net/publication/224201475_Fidelity_Metrics_for_Estimation_Models>

71. Statistics - Fidelity Capital Markets, accessed on July 21, 2025, <https://capitalmarkets.fidelity.com/trade-execution-quality/statistics>
