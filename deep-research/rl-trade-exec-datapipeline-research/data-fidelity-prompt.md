## **Research Prompt: Ensuring Data Fidelity for RL Backtesting Environment**

### **1. Research Objective**

To define a comprehensive data processing and simulation strategy that guarantees the historical data used for backtesting the RLX Co-Pilot agent is structurally and behaviorally identical to the real-time data it will encounter in a live trading environment. The outcome of this research will be a "Data Fidelity & Synchronization Strategy" document that will serve as the blueprint for the data pipeline's requirements.

### **2. Key Research Areas & Questions**

#### **Area A: Understanding the Data Source (Crypto Lake)**

The goal here is to understand the exact nature and limitations of our raw materials.

1.  **Timestamping & Synchronization:**
    * What exactly does `origin_time` represent for Crypto Lake's `book` data (L2 snapshots) vs. `trades` data? Is it the exchange event time, the time the data was collected by Crypto Lake, or the time it was written to their storage?
    * Is there a guaranteed chronological consistency between a trade at time `T` and an L2 snapshot at time `T`? For example, if a trade occurs at `T`, is the L2 snapshot at `T` guaranteed to reflect the state of the book *after* that trade? Or could it be before?
    * What is the stated latency or potential delay between the actual exchange event and its appearance in the Crypto Lake dataset?

2.  **L2 Snapshot Generation:**
    * How are Crypto Lake's L2 snapshots generated? Are they event-driven (a new snapshot on every book change) or time-driven (a snapshot every X milliseconds)?
    * What is the typical frequency/granularity of snapshots for a liquid pair like BTC-USDT on Binance?
    * Does a "snapshot" represent the complete book state at an instant, or is it an aggregation over a small time window?

#### **Area B: Characterizing the Real-Time Target Environment (Binance)**

The goal is to define the "ground truth" that our simulation must replicate.

1.  **Real-Time Websocket Feed Structure:**
    * What is the exact data structure of a real-time L2 order book update message (`@depth`) from the Binance WebSocket API?
    * What is the exact data structure of a real-time trade message (`@trade`) from the Binance WebSocket API?
    * How are these two streams synchronized in real-time? Do they share a common sequence number or timestamping convention that guarantees their order?

2.  **Combining Real-Time Streams:**
    * In a live production environment, would we process trades and book updates as a single, interleaved stream of events? Or would we maintain two separate states (the book and the trade history)? What is the industry best practice for this?
    * Should our simulated environment yield a single, unified "market event" at each time step (which could be a trade *or* a book update), mimicking a real-time event loop?

#### **Area C: Strategy for High-Fidelity Data Reconstruction**

The goal is to define the specific methods we will use to make our backfill data match the real-time target.

1.  **Data Unification Strategy:**
    * Based on findings from A & B, what is the best strategy to merge the backfilled trades and L2 snapshots into a single, chronologically accurate event stream?
    * Should we use the L2 snapshots as the primary "clock" and inject trades between them based on timestamps?
    * Or, is it better to start with an initial L2 snapshot and then "rebuild" the book state forward in time by applying every single trade and book update event from a more granular (L3-like) data source, if available?
    * What are the pros and cons of interpolating the book state between snapshots?

2.  **Validating Fidelity:**
    * How can we design a quantitative test to compare our reconstructed historical event stream against a sample of captured real-time data?
    * What specific metrics should we use for this comparison? (e.g., comparing distributions of inter-event timings, trade sizes, book depth, etc.).
    * Should a key deliverable of the data pipeline be a "Fidelity Report" that runs this comparison and outputs a similarity score?

### **3. Expected Deliverables from this Research**

1.  A clear, documented decision on **how to process and combine the backfilled data** to create a single, unified event stream for the simulation.
2.  The **exact schema** for this unified "market event" data structure.
3.  A **validation plan** describing how we will prove that the simulated environment's data feed matches the real-time environment's data feed.