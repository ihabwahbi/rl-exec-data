# **A Framework for Agile Fidelity Refinement: A Prescriptive Workflow for the RLX Co-Pilot Project**

### **Executive Summary**

**Problem Statement**: The RLX Co-Pilot project requires a robust agile workflow to manage the iterative refinement of the Reconstructor data generation engine, driven by systematic validation from the FidelityReporter. The core challenge is to efficiently converge on a high-fidelity data product by managing the feedback loop of testing, triaging, fixing, and re-testing. This phase of the project necessitates a departure from conventional software development workflows toward a specialized process tailored for the continuous validation of a complex data asset.

**Core Recommendation: The Integrated Fidelity Refinement (IFR) Workflow**: This report recommends the adoption of an **Integrated Fidelity Refinement (IFR) Workflow**. This is a bespoke agile model, grounded in MLOps Level 2 principles and adapted from the Scrum framework, designed specifically for the continuous validation and refinement of data products. It advocates for **Integrated Refinement Sprints** over alternating sprint structures to maximize the velocity of the feedback loop, which is the most critical factor for success in a convergence-focused project.

**Key Pillars of the IFR Workflow**:

1. **Sprint Structure**: Two-week, integrated sprints containing a prioritized mix of Fidelity Defect and Metric Implementation stories. This structure enables a rapid, intra-sprint feedback loop where new tests can be added, failures observed, and fixes implemented within a single iteration, dramatically accelerating the overall refinement process.

2. **Prioritization**: A quantitative **Fidelity Value Score (FVS)** framework to objectively prioritize work. This model provides a data-driven method for balancing the remediation of severe data defects against the implementation of new validation metrics, ensuring that engineering effort is consistently applied to the tasks that most effectively advance the project toward its fidelity goals.

3. **Triage & RCA**: A formal, multi-stage triage process for all validation failures. This process incorporates structured Root Cause Analysis (RCA) techniques to systematically diagnose whether a failure originates in the Reconstructor, the FidelityReporter, the source data, or the underlying infrastructure, thereby preventing wasted engineering cycles on misdiagnosed issues.

4. **Convergence Tracking**: A multi-layered **Definition of Done** for Epic 3, culminating in a requirement for sustained data fidelity over multiple pipeline runs. Progress is tracked via a primary **Fidelity Score Burn-Up Chart**, which transparently visualizes both the completion of work and the expansion of validation scope. This is supplemented by secondary visualizations like Test Pass Rate Trends and Defect Discovery vs. Resolution Rates to provide a comprehensive view of project health.

**Expected Business Outcome**: The adoption of the IFR workflow will de-risk Epic 3 by providing a predictable, transparent, and efficient process for achieving the target data fidelity. This structured approach will reduce wasted engineering cycles, improve team morale by providing clear measures of progress, and accelerate the time-to-value for the RLX Co-Pilot data product. The deliverables from this process are not just a high-fidelity Reconstructor, but also a reusable, automated Fidelity Refinement system that represents a significant step forward in the organization's MLOps maturity.

***


### **Part I: Foundational Principles of Continuous Validation and Refinement**

This section establishes the theoretical and industry-proven groundwork for the proposed workflow. It synthesizes principles from Machine Learning Operations (MLOps), Data Operations (DataOps), and Test-Driven Development (TDD) to create a coherent philosophical foundation for the specific recommendations that follow.


#### **1.1. The MLOps Imperative: From Manual Processes to Automated Pipelines**

The challenge facing the RLX Co-Pilot project is a classic microcosm of the journey from a nascent, manual development process to a mature, automated operational model. This evolution is well-documented in the MLOps maturity framework, which describes a progression from Level 0 (manual processes) to Level 2 (automated CI/CD).<sup>1</sup> MLOps Level 0 is characterized by a "disconnection between ML and operations," where data scientists or engineers manually create a model (or in this case, a data generator) and hand it over as an artifact for deployment. This approach is fraught with peril, often leading to issues like "training-serving skew," where the system behaves differently in production than it did in development due to environmental or data differences.<sup>1</sup> Epic 3 represents an explicit and necessary effort to transcend this manual stage.

The goal is to implement a system capable of **Continuous Training (CT)** and **Continuous Delivery (CD)**, not just of a software artifact, but of the _data product itself_. This requires orchestrating the Reconstructor and FidelityReporter into a single, automated pipeline where the output of one seamlessly becomes the input for the other.<sup>1</sup> The core principles of MLOps—advocating for automation and monitoring at all steps of system construction, including integration, testing, releasing, and deployment—are therefore not merely optional best practices but are prerequisites for the success of this epic.<sup>1</sup>

This endeavor sits at the intersection of MLOps and DataOps. While MLOps focuses on the lifecycle management of the machine learning components like the Reconstructor, DataOps provides the principles for managing the data workflow itself, including ingestion, processing, quality, and governance.<sup>4</sup> A successful outcome depends on the tight integration of these two disciplines. This integration fosters collaboration, establishes shared goals, and ensures that data flows seamlessly from generation through validation, minimizing manual handoffs and enabling teams to work in parallel rather than in silos.<sup>4</sup> The workflow architected for Epic 3 must embody this synthesis, creating a unified process for a unified team.


#### **1.2. Continuous Validation as a Core Tenet**

Continuous Validation is a discipline derived from DevOps that ensures the integrity, performance, and reliability of machine learning systems throughout their entire lifecycle.<sup>2</sup> For Epic 3, this translates directly to the practice of continuously validating the output of the

Reconstructor against the evolving and expanding test suite of the FidelityReporter. This is not a one-time quality check but an ongoing, automated process that forms the heartbeat of the refinement cycle.

The essential mechanisms that enable Continuous Validation are **automated pipelines** and **feedback loops**.<sup>2</sup> The pipeline automates the execution sequence: the

Reconstructor generates data, which is then immediately fed into the FidelityReporter for validation. The feedback loop is the process by which the results of this validation—the pass/fail status of the fidelity metrics—are captured, analyzed, and used to inform the next iteration of development on the Reconstructor.<sup>6</sup>

A critical function of this automated pipeline is the validation of both data schema and data values.<sup>1</sup> While schema validation ensures structural correctness (e.g., correct data types, no missing columns), the more sophisticated task for the

FidelityReporter falls under value validation. The complex statistical tests it will perform are a form of "data values skew" detection. A failure on one of these tests is a definitive signal that the statistical properties of the generated data do not align with those of the "golden sample" data. This automated detection is the trigger that initiates the entire refinement cycle, deciding whether to halt the process for investigation or, in a fully mature MLOps system, even automatically trigger a retraining or tuning run.<sup>1</sup>


#### **1.3. Adapting Development Paradigms: From TDD to Fidelity-Driven Refinement (FDR)**

To manage the iterative cycle of testing and fixing, established software development paradigms provide powerful mental models that can be adapted to this data-centric problem.

**Test-Driven Development (TDD)** offers a tactical, micro-level approach. In TDD, a developer first writes a test that codifies a desired feature, ensures it fails (because the feature doesn't exist yet), and only then writes the minimum amount of code required to make the test pass. This is often called the "Red-Green-Refactor" cycle.<sup>7</sup> This maps perfectly to the RLX Co-Pilot's challenge:

- **Red**: Implementing a new statistical metric in the FidelityReporter is equivalent to writing a new, failing test. The Reconstructor's initial output is expected to fail this test.

- **Green**: The subsequent work to tune or debug the Reconstructor is the act of writing the "code" to make that specific test pass.

- **Refactor**: Once the test is passing, the code can be refined for efficiency and clarity.

While TDD provides the tactical loop, the academic concept of **Iterative Refinement** provides the strategic guidance. This strategy, proposed in the context of automating ML pipeline design, advocates for focusing on one component at a time rather than making sweeping, simultaneous changes.<sup>8</sup> By systematically updating individual components based on real feedback, this approach leads to more stable, interpretable, and controlled improvements. It allows performance changes to be directly attributed to specific adjustments, which accelerates convergence and prevents redundant modifications.<sup>8</sup>

Synthesizing these two paradigms yields a guiding philosophy for Epic 3, which can be termed **Fidelity-Driven Refinement (FDR)**. The core loop of FDR is a disciplined, four-step process:

1. **Define Fidelity**: Implement a new statistical test (a "Metric") in the FidelityReporter. This establishes a new, testable requirement for data quality.

2. **Measure Fidelity**: Execute the automated pipeline, running the Reconstructor and FidelityReporter. Observe and log the expected failure of the newly implemented metric. This is the "Red" state.

3. **Refine Reconstructor**: Triage the failure through a formal Root Cause Analysis process. If the cause is a flaw in the Reconstructor, create a "Fidelity Defect" work item to schedule the fix.

4. **Achieve Fidelity**: Implement the required fix in the Reconstructor, re-run the pipeline, and confirm that the test now passes. This is the "Green" state.

Framing the work of Epic 3 through the lens of MLOps maturity and the FDR principle elevates its strategic importance. The objective is not merely to perform a series of bug fixes. Rather, it is to construct a durable, automated, and reusable _Fidelity Refinement system_. The primary deliverable is not just a "fixed" Reconstructor but a mature MLOps capability that can be applied to future data products, representing a lasting increase in the organization's technical and operational prowess.

***


### **Part II: Architecting the Fidelity Refinement Workflow**

This section presents the core operational model for Epic 3. It analyzes two distinct agile sprint structures and provides a definitive, justified recommendation for the RLX Co-Pilot team. This architecture is designed to translate the foundational principles from Part I into a concrete, day-to-day process.


#### **2.1. Analysis of Sprint Structure Models**

Agile methodologies like Scrum, with their time-boxed sprints, defined roles, and regular ceremonies, provide a robust starting point for managing complex work.<sup>9</sup> However, the unique challenges of data science and machine learning projects—which are often characterized by deep uncertainty, research-heavy tasks, and unpredictable results—necessitate careful adaptation of these frameworks.<sup>9</sup> The most critical architectural decision for Epic 3 is how to structure the sprints to efficiently manage the two primary, interdependent workstreams: building new validation capabilities in the

FidelityReporter and fixing the data generation flaws in the Reconstructor.


##### **Model A: Alternating Sprints (Validation vs. Refinement)**

- **Description**: In this model, the team would alternate between two distinct types of sprints. A "Validation Sprint," lasting perhaps one or two weeks, would be dedicated exclusively to implementing new metrics in the FidelityReporter (i.e., Metric Implementation stories). The subsequent "Refinement Sprint" would then be dedicated exclusively to fixing the bugs and flaws that were uncovered during the prior validation sprint (i.e., Fidelity Defect stories).

- **Pros**: The primary advantage of this model is its simplicity and focus. During a Validation Sprint, the team can concentrate fully on the statistical and software engineering challenges of building robust tests. During a Refinement Sprint, they can apply deep focus to debugging the complex logic of the Reconstructor. This separation can reduce cognitive load and simplify sprint planning, as the goal for each sprint is monolithic and unambiguous.

- **Cons**: The most significant and likely fatal drawback of this model is the high degree of **feedback latency** it introduces. A critical fidelity defect discovered on the first day of a two-week Validation Sprint might not even be scheduled for work until the _following_ two-week Refinement Sprint begins, introducing a delay of up to four weeks between defect discovery and resolution. This slow cycle time runs directly counter to the agile principle of "Fail fast, fail often!" <sup>6</sup> and would severely hamper the rate of convergence. Furthermore, this structure risks creating a "throw it over the wall" mentality, where the work of validation is seen as separate from the work of refinement, undermining the collaborative, single-team ethos required for success.


##### **Model B: Integrated Refinement Sprints (Recommended)**

- **Description**: This model, which will be referred to as the **Integrated Fidelity Refinement (IFR) Sprint**, treats the entire epic as a single, unified effort. Each sprint is a self-contained, fixed-length time-box (e.g., two weeks) that contains a carefully prioritized mix of _both_ Metric Implementation stories and Fidelity Defect stories.<sup>12</sup>

- **Pros**: The paramount advantage of the IFR model is its ability to **minimize feedback latency**. A new metric can be implemented, the corresponding failure can be observed, the issue can be triaged, and a fix can be developed and verified, all potentially _within the same sprint_. This creates an extremely rapid iterative cycle, which is the single most important factor for achieving convergence efficiently. This model fosters a more holistic and collaborative team mindset, as all members are working toward the unified goal of improving total system fidelity, rather than focusing on isolated components. It also provides far greater flexibility to respond to high-severity defects as they are discovered, without waiting for a designated "refinement" period.

- **Cons**: The primary challenge of the IFR model is the increased complexity of sprint planning. The Product Owner and the team must make more nuanced trade-offs when selecting work for the sprint, balancing the need to expand test coverage against the urgency of fixing known defects. This challenge, however, is a manageable trade-off that can be effectively mitigated with the robust, quantitative prioritization framework detailed in Part III of this report.

The following table provides a clear, at-a-glance justification for the report's central workflow recommendation, allowing decision-makers to quickly understand the trade-offs involved and the rationale behind choosing the IFR model.

|                      |                                              |                                                                      |                                                                                              |
| -------------------- | -------------------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Feature              | Model A: Alternating Sprints                 | Model B: Integrated Refinement Sprints (IFR)                         | Justification                                                                                |
| **Primary Goal**     | Maximize single-task focus                   | Maximize feedback velocity                                           | IFR's goal directly supports the epic's need for rapid convergence.                          |
| **Feedback Latency** | High (2-4 weeks)                             | Low (Intra-sprint, <2 weeks)                                         | Lower latency is critical for efficient refinement and risk reduction.<sup>6</sup>           |
| **Sprint Planning**  | Simpler (monolithic goal)                    | More Complex (balancing two work types)                              | Complexity is a manageable trade-off, addressed by the FVS framework in Part III.            |
| **Team Mindset**     | Risk of "Validation" vs. "Refinement" siloes | Fosters a unified team focused on total system fidelity.<sup>4</sup> | A unified mindset is crucial for collaborative problem-solving.                              |
| **Adaptability**     | Lower (a critical defect may wait weeks)     | Higher (can pivot to fix critical defects immediately)               | High adaptability is essential when the nature and severity of defects are unknown.          |
| **Recommendation**   | Not Recommended                              | **Recommended for Epic 3**                                           | The IFR model is optimally aligned with the core project objective of efficient convergence. |


#### **2.2. The Recommended IFR Sprint Structure and Ceremonies**

Based on the analysis, this report strongly recommends the adoption of **Model B: The Integrated Fidelity Refinement (IFR) Sprint**. The strategic advantage of a rapid feedback loop outweighs the manageable complexity of integrated planning. The ability to shorten the cycle from test creation to defect resolution is the key to unlocking project velocity and mitigating the risk of slow, unpredictable progress.

- **Sprint Cadence**: Sprints should be fixed at a **two-week** duration.<sup>10</sup> This cadence is a widely adopted standard that is short enough to maintain agility and respond to new information, yet long enough for the team to complete a meaningful bundle of work, including both metric implementation and defect resolution.

- **Adapted Scrum Ceremonies for IFR**: The standard Scrum ceremonies provide the essential structure for inspection and adaptation, but their content and focus must be tailored to the specific goals of the IFR workflow.<sup>15</sup>

* **Sprint Planning** <sup>14</sup>: This ceremony marks the start of the sprint. The Product Owner presents the highest-priority items from both the\
  Metric Implementation backlog and the triaged Fidelity Defect backlog. The team collaborates to forecast the work they can pull into the sprint, using the **Fidelity Value Score (FVS)** (detailed in Part III) as a primary guide for prioritization, balanced against their known capacity. A key output of this meeting is a hybrid **Sprint Goal**. For example: _"By the end of this sprint, we will implement the 'Kolmogorov-Smirnov' and 'Correlation Matrix' fidelity metrics in the FidelityReporter, and we will resolve all 'Critical' and 'High' severity defects related to the volatility surface generator, increasing our overall Fidelity Score by at least 15 points."_

* **Daily Scrum** <sup>10</sup>: The standard 15-minute daily stand-up meeting remains crucial for coordination. The focus of the conversation will be on progress toward the hybrid sprint goal and identifying any blockers that are impeding either metric implementation or defect resolution.

* **Sprint Review** <sup>9</sup>: This ceremony is critically important and requires a significant adaptation from a traditional software demo. Since the "increment" being produced is an improvement in data fidelity—an abstract concept—the review cannot focus on new user interface elements. Instead, the Sprint Review becomes a\
  **Fidelity Progress Review**. The team demonstrates progress by showcasing the output of the FidelityReporter itself. The demonstration will have two parts: 1) showing the newly implemented metrics and their corresponding (and expected) initial failures against the Reconstructor's output, and 2) showing the now-passing status of metrics that were previously failing but have been addressed by the Fidelity Defect fixes completed during the sprint. The central artifact for this meeting will be the **Convergence Dashboard** and its **Fidelity Score Burn-Up Chart** (detailed in Part IV), which visually communicates the progress made. Stakeholders must be educated that their role in this review is to provide feedback on the business impact of the remaining fidelity gaps, rather than on UI/UX features.

* **Sprint Retrospective** <sup>9</sup>: This is the team's opportunity to inspect and adapt its own process. The retrospective will focus on the effectiveness of the IFR workflow itself. Key questions to explore include:\
  _"Is our triage process for new failures efficient and accurate?"_, _"Are our effort estimates for Fidelity Defects becoming more reliable?"_, _"Is the Fidelity Value Score framework helping us make the right prioritization decisions?"_, and _"What is the biggest impediment to our convergence velocity?"_

By adopting this integrated sprint structure and adapting the ceremonies to focus on fidelity, the team can create a powerful, rhythmic process for systematically driving the data product to the required level of quality.

***


### **Part III: Backlog Management and Prioritization Strategy**

This section provides the specific, tactical mechanisms for creating, triaging, and prioritizing the work that will flow through the Integrated Fidelity Refinement (IFR) sprints. A disciplined approach to backlog management is essential to manage the complexity of the IFR model and ensure that engineering efforts are always directed at the most valuable tasks.


#### **3.1. Structuring the Fidelity Backlog: From Epics to Stories**

The work for Epic 3 should be broken down into clear, well-defined user stories. The user story format is highly effective because it forces the team to frame every piece of work in terms of the value it delivers to a specific persona, keeping the focus on outcomes rather than just tasks.<sup>18</sup> For this epic, two primary types of user stories will be used.

- **Type 1: Metric Implementation Story**

* **Purpose**: This story type is used to track the work of adding a new statistical test or validation rule to the FidelityReporter. Each story represents an expansion of the project's quality assurance capabilities.

* **User Story Template** <sup>18</sup>:As a **Data Fidelity Analyst**, I want to **implement the on the** so that **we can verify that the Reconstructor's output distribution matches the golden sample's distribution.**

* **Acceptance Criteria**: The acceptance criteria for a Metric Implementation story will be technical and precise. They should include details such as the specific statistical library to be used, the p-value threshold that defines a failure, the required format for logging results, and confirmation that the new metric is integrated into the automated pipeline.

- **Type 2: Fidelity Defect Story**

* **Purpose**: This story type is used to document and track the work required to fix the Reconstructor so that it can pass one or more failing fidelity metrics. It is the direct output of the triage process and functions as a specialized bug report.<sup>21</sup>

* **Creation**: Crucially, these stories are only created _after_ the formal Triage and Root Cause Analysis process (detailed in Section 3.3) has definitively identified a flaw within the Reconstructor.

* **User Story Template**:As a **System User**, I want the **Reconstructor to generate data that passes the \[Failing Metric Name]** so that **the synthetic data is a statistically valid and reliable representation of the real-world data for downstream processes.**

* **Details**: This user story serves as the high-level work item in the backlog. It must be linked to a more detailed **Fidelity Defect Report** (see template in Part V) which contains the comprehensive technical details, including the full Root Cause Analysis, logs, and diagnostic outputs necessary for the development team to effectively address the issue.


#### **3.2. The Fidelity Value Score (FVS): A Hybrid Prioritization Framework**

The central challenge in planning an IFR sprint is deciding how to prioritize between fixing known data quality issues (Fidelity Defects) and implementing new tests to find unknown issues (Metric Implementation). A simple qualitative assessment is insufficient and prone to bias.<sup>22</sup> A quantitative, data-driven framework is required to make this complex trade-off explicit and defensible.

This report proposes the **Fidelity Value Score (FVS)**, a scoring model adapted from established prioritization frameworks like Weighted Scoring and Value vs. Effort.<sup>23</sup> The FVS provides a single, comparable score for

_every_ story in the backlog, regardless of its type, allowing for a unified ranking.

- FVS Formula: The score for each story is calculated as follows:\
  \
  FVS=Effort(Impact×Confidence)​

- **Component Definitions**:

* **Impact (scale 1-100)**: This score represents the direct value or importance of completing the story. Its meaning differs slightly based on the story type.

- For a **Fidelity Defect**, Impact is primarily driven by **Severity**. The team can adapt a standard severity scale, such as Atlassian's <sup>21</sup>:

* **Critical (90-100)**: The defect causes a complete failure of a downstream process, generates corrupted or unusable data (e.g., NaNs), or represents a massive deviation in a mission-critical financial variable.

* **Major (60-89)**: The defect causes a significant and measurable statistical deviation in a key data feature, which would lead to incorrect conclusions or model behavior.

* **Minor (1-59)**: The defect represents a slight statistical deviation in a less critical feature or has a workaround.

- For a **Metric Implementation**, Impact is driven by **Metric Value**. This is an assessment of how critical the new test is to the overall business objective of achieving data fidelity. Is it a foundational test of a core data property (high value), or a more nuanced test of a secondary property (lower value)?

* **Confidence (scale 1-100)**: This is a multiplier that accounts for the broader, secondary benefits and uncertainties associated with the story.

- For a **Fidelity Defect**, Confidence is the **Convergence Factor**. This estimates the likelihood that fixing this single defect will cause _multiple_ other failing tests to pass simultaneously. A fix to a fundamental, upstream module in the Reconstructor's logic might have a very high Convergence Factor, as it could resolve a whole class of related errors.

- For a **Metric Implementation**, Confidence is the **Coverage Expansion**. This score quantifies how much new "validation surface area" the new metric will cover. A test that validates a completely new domain of the data that is currently untested would receive a high score, whereas a test that is a minor variation of an existing test would receive a lower score.

* **Effort (T-Shirt sizes converted to numerical points)**: This is the standard agile estimation of the complexity, time, and resources required to complete the story. A Fibonacci-like scale is recommended (e.g., XS=1, S=2, M=3, L=5, XL=8).<sup>9</sup>

- **Process**: During backlog refinement sessions, the entire team (Product Owner, developers, data scientists) collaborates to discuss and assign scores for Impact, Confidence, and Effort to each story in the backlog. The FVS is then automatically calculated. This process transforms prioritization from a subjective debate into a structured, data-informed exercise. The Product Owner can then use the FVS-sorted backlog to propose the most valuable work for the upcoming sprint, providing a transparent and defensible rationale for the plan.


#### **3.3. A Formal Triage Strategy for Validation Failures**

When the automated pipeline runs and the FidelityReporter flags a new failure, it is essential to avoid the knee-jerk reaction of assuming the Reconstructor is at fault. A systematic triage process is the most critical risk-mitigation strategy for this epic, preventing the team from wasting precious engineering cycles fixing the wrong problem.

- **Step 1: Automated Failure Logging and Alerting**: The MLOps pipeline must be configured for robust error containment and observability.<sup>26</sup> Every validation failure must be automatically logged with rich, contextual metadata: the name of the failing metric, the timestamp, a unique ID for the data batch being tested, the specific values that caused the failure, and a link to the validation report. This event must trigger an immediate alert to a designated channel (e.g., a specific Slack channel or PagerDuty rotation) to ensure prompt attention.

- **Step 2: Initial Diagnosis (The Triage Meeting)**: A small, designated triage team—typically consisting of the Tech Lead, a senior data scientist, and a senior engineer—should convene for a brief, time-boxed meeting to conduct an initial diagnosis of the failure. The sole purpose of this meeting is to form a hypothesis about the likely source of the error and decide on the appropriate next step for a deeper investigation.

- **Step 3: Structured Root Cause Analysis (RCA)**: Based on the initial diagnosis, the team must employ a structured RCA method to definitively pinpoint the underlying cause of the failure. This is not an informal process; it is a disciplined investigation. Two methods are particularly well-suited for this context:

* **The Five Whys** <sup>28</sup>: This technique is excellent for drilling down into process or logic failures by repeatedly asking "Why?". For example:\
  _"Why did the Kurtosis test fail?" -> "Because the generated distribution has excessively fat tails." -> "Why does it have fat tails?" -> "Because the stochastic volatility component in the generator is over-reacting to outliers in the input noise." -> "Why is it over-reacting?" -> "Because its dampening parameter is not properly constrained."_ This process moves from symptom to root cause.

* **Fishbone (Ishikawa) Diagram** <sup>28</sup>: This visual tool is ideal for complex failures where multiple potential causes exist. The "head" of the fish is the problem (e.g., "Volatility Smile Skewness Test Failed"). The "bones" of the fish represent predefined categories of potential causes, which for this project should be:

1. **Reconstructor Flaw**: A genuine bug, algorithmic error, or incorrect implementation in the data generation logic.

2. **FidelityReporter Flaw**: An error in the validation logic itself, such as using the wrong parameters for a statistical test, a bug in the library call, or an incorrect implementation of the test's formula.

3. **Golden Sample Artifact**: The "failure" is not a failure at all, but rather an accurate reflection of an anomaly, outlier, or non-representative data point within the source "golden" dataset that is being used as the benchmark.

4. **Pipeline/Environment Issue**: The failure was caused by an external factor, such as a corrupted data read from storage, an incorrect version of a shared library being loaded, or a network issue that prevented complete data access.

- **Step 4: Disposition and Work Item Creation**: The outcome of the RCA determines the final disposition of the failure, which in turn dictates the next action.

* If the cause is a **Reconstructor Flaw**, a new **Fidelity Defect Story** is created in the backlog, complete with the RCA summary and all supporting evidence.

* If the cause is a **FidelityReporter Flaw**, a standard bug ticket is created and assigned to be fixed within the validation engine's codebase.

* If the cause is a **Golden Sample Artifact**, a data analysis task is created to investigate the source data, which may lead to data cleaning, removal of the artifact, or an adjustment to the validation test to ignore it.

* If the cause is a **Pipeline/Environment Issue**, the issue is escalated to the responsible platform or DevOps team for resolution.

This formal triage and RCA process is the bedrock of the IFR workflow. It ensures that development effort is precisely targeted, building confidence that the team is always working on the right problem at the right time.

***


### **Part IV: Defining and Tracking Convergence**

This section details how project success is formally defined and measured. It provides a comprehensive "Definition of Done" for the entire epic and specifies the key visualizations required to track progress transparently and communicate status effectively to all stakeholders.


#### **4.1. The Multi-Layered "Definition of Done" (DoD) for Epic 3**

For a complex, multi-faceted project like Epic 3, a single, simple Definition of Done is insufficient. A hierarchical DoD is necessary to ensure that quality and completeness are built in at every level of the process, from individual tasks to the final project outcome.<sup>9</sup>

- **Layer 1: Story-Level DoD**: This definition applies to every individual story (Metric Implementation or Fidelity Defect) pulled into a sprint. A story is considered "Done" only when:

* All associated code has been written, has passed automated checks, has been peer-reviewed, and is successfully merged into the main development branch.

* All relevant unit and integration tests for the new or modified code are passing.

* **For a Fidelity Defect story**: The specific fidelity metric(s) that the story was created to address now report a "Pass" status in an automated pipeline run.

* **For a Metric Implementation story**: The new metric is fully implemented and active in the FidelityReporter, its documentation is complete, and it is integrated into the automated validation pipeline.

- **Layer 2: Sprint-Level DoD**: A sprint is considered "Done" only when:

* All user stories that were committed to during Sprint Planning have met the Story-Level DoD.

* The overarching Sprint Goal, as defined during Sprint Planning, has been successfully achieved.

* The Sprint Review ceremony has been conducted, the progress has been demonstrated to stakeholders, and all feedback has been captured and logged for consideration in future planning.

- **Layer 3: Epic-Level DoD (The Final Goal)**: This is the ultimate set of success criteria that signifies the completion of the entire Epic 3. The epic is considered "Done" only when all of the following conditions are met:

1. **Metric Completeness**: 100% of the Metric Implementation stories that were defined in the project's initial backlog have been completed and deployed to the FidelityReporter. This ensures that the full, intended scope of validation has been achieved.

2. **Fidelity Convergence**: The data output from the Reconstructor achieves a **100% pass rate** against all active metrics in the FidelityReporter. This 100% pass rate must be maintained for a predefined number of consecutive, automated pipeline runs (e.g., over a 24-hour period) to ensure stability and rule out intermittent failures or successes due to chance. This demonstrates that the Reconstructor is not just capable of passing the tests, but is robustly and reliably correct.

3. **Documentation Completeness**: All key components (Reconstructor, FidelityReporter) and processes (the IFR workflow, the Triage and RCA process) are fully documented, ensuring the system is maintainable and the process is repeatable for future projects.

This multi-layered DoD provides clarity at all levels and ensures that the final product is not only functionally complete but also stable, reliable, and well-documented. The requirement for sustained convergence over time is particularly important, as it proves the robustness of the solution beyond a single successful test run.


#### **4.2. Visualizing Progress: The Convergence Dashboard**

To effectively track progress towards the Epic-Level DoD, the team must create and maintain a "single source of truth" dashboard.<sup>26</sup> This dashboard will provide an immediate, at-a-glance understanding of the project's status for all stakeholders, from the development team to senior leadership. It should be composed of several key visualizations.

- **Primary Visualization: Fidelity Score Burn-Up Chart**

* **Purpose**: The burn-up chart is the single most important visualization for this epic. It is superior to a burn-down chart because it is explicitly designed to track progress toward a goal while simultaneously visualizing changes in the total scope of the project.<sup>30</sup> This is a perfect fit for Epic 3, where the team is both completing work (fixing defects) and adding to the scope (implementing new metrics). A burn-down chart would be misleading, as each new metric would make the "remaining work" line jump up, obscuring true progress.<sup>30</sup>

* **Structure** <sup>30</sup>:

- **X-Axis**: Time, measured in days or sprints.

- **Y-Axis**: Aggregate Fidelity Score. This is a quantitative measure of fidelity, calculated as the sum of the "Metric Value" (from the FVS framework) for all defined metrics.

- **Line 1 (Total Scope)**: This line represents the total possible fidelity score. It starts at zero and **steps up** each time a Metric Implementation story is completed, visually representing the expanding scope of validation. Its final value will be the sum of all metric values in the project.

- **Line 2 (Achieved Fidelity)**: This line represents the current fidelity score of the Reconstructor. It is calculated as the sum of the "Metric Value" for all metrics that are currently **passing**. This line will climb upwards as Fidelity Defect stories are completed and resolved.

* **Interpretation**: The project's progress is visualized by the "Achieved Fidelity" line chasing the "Total Scope" line. The gap between the two lines represents the current "fidelity debt"—the amount of known, validated quality issues remaining. The epic is formally "Done" when the green "Achieved Fidelity" line finally meets the red "Total Scope" line and stays there, signifying 100% passing metrics.

- **Secondary Visualizations**: While the burn-up chart is the primary indicator, several supplementary charts provide additional diagnostic insight into the health of the process.

* **Test Pass Rate Trend Chart**: This is a simple line graph that plots the percentage of total implemented tests that are passing at any given point in time.<sup>32</sup> This provides a more intuitive, non-weighted view of progress that is easy for all stakeholders to understand. A dip in this chart is a normal and expected event whenever a new batch of metrics is added to the\
  FidelityReporter. The key trend to monitor is the subsequent recovery and steady upward climb of the pass rate.

* **Defect Discovery vs. Resolution Rate Chart**: This is a cumulative flow diagram or a dual-axis line chart that tracks two key metrics over time. One line plots the cumulative number of Fidelity Defects created (the Discovery Rate). The second line plots the cumulative number of Fidelity Defects closed (the Resolution Rate). For the project to be on a path to convergence, the slope of the resolution line must be consistently steeper than the slope of the discovery line. If the discovery rate outpaces the resolution rate for a sustained period, it is a strong signal that the project is falling behind and that the team's process or capacity needs to be re-evaluated.

Together, these visualizations form a comprehensive Convergence Dashboard that makes progress tangible, holds the team accountable, and provides early warning signals of potential problems, enabling proactive management of the entire epic.

***


### **Part V: Implementation Toolkit**

This final section provides the concrete, actionable artifacts required to implement the Integrated Fidelity Refinement (IFR) workflow. It includes detailed templates for work items and a targeted analysis of supporting tools and relevant external contexts, designed to make the proposed framework immediately operational for the RLX Co-Pilot team.


#### **5.1. Template: The Fidelity Defect Story**

This work item is a specialized and structured bug report, designed to be created in a project management tool like Jira. It should be created only after the formal triage and Root Cause Analysis (RCA) process is complete. The template synthesizes best practices for effective bug reporting to ensure clarity, context, and actionability.<sup>34</sup>

- **Issue Type**: Fidelity Defect (This should be a custom issue type in your tracking tool).

- **Title**: \[Component]:

* _Example_: Reconstructor-VolGen: Generated volatility smile exhibits excessive kurtosis

- **Fields**:

* **User Story**: As a System User, I want the Reconstructor to generate data that passes the \[Failing Metric Name] so that the synthetic data is a statistically valid representation of the real-world data.

* **Failing Metric(s)**: Link(s) to the specific FidelityReporter metric(s) that are failing.

* **Severity**: (Classification based on the definitions in Part III, adapted from <sup>21</sup>).

* **Environment**:

- Reconstructor Version: \[e.g., v1.2.3-alpha]

- FidelityReporter Version: \[e.g., v0.9.1]

- Golden Sample ID: \[e.g., gs\_q1\_2024\_final]

* **Root Cause Analysis Summary**: A concise, one-paragraph summary of the RCA findings from the triage process. This field is mandatory and ensures that no defect is worked on without a proper investigation.<sup>28</sup>

- _Example_: "The Five Whys analysis determined that the SABR model calibration routine within the Reconstructor is not properly constraining the beta parameter, allowing it to drift to extreme values. This results in the generation of distributions with fat tails, causing the failure of the 'Kurtosis Range Check' metric."

* **Expected Result**: The failing metric(s) should report a "Pass" status with a p-value greater than the defined threshold (e.g., > 0.05).

* **Actual Result**: The \[Metric Name] metric reports a "Fail" status with a p-value of \[value]. Diagnostic output: \[Paste relevant logs or error messages here].

* **Fidelity Value Score (FVS)**:

- Impact: \`\`

- Confidence: \`\`

- Effort: \`\`

- **FVS**: \[Auto-calculated]

* **Acceptance Criteria**:

- \[ ] The code fix is implemented in the \`\` of the Reconstructor.

- \[ ] New unit tests covering the corrected logic are added and pass.

- \[ ] When the full validation pipeline is executed, the \[Failing Metric Name] now passes.

- \[ ] No new metric failures (regressions) have been introduced by this change.

This structured template is more than just a documentation tool; it is a process enforcement mechanism. By requiring fields like the RCA Summary and the FVS Score, it ensures that the team adheres to the prescribed triage and prioritization workflows before any development work commences.


#### **5.2. Template: The Metric Implementation Story**

This is a standard feature or task story, specifically tailored for tracking the addition of new validation capabilities to the FidelityReporter. It focuses on the value and specification of the new test.<sup>18</sup>

- **Issue Type**: Story

- **Title**: FidelityReporter: Implement \[Metric Name]

* _Example_: FidelityReporter: Implement 2-Sample Anderson-Darling Test

- **Fields**:

* **User Story**: As a Data Fidelity Analyst, I want to implement the on the so that we can verify \`\`.

- _Example_: As a Data Fidelity Analyst, I want to implement the 2-Sample Anderson-Darling test on the term structure of interest rates so that we can verify that the generated curve's distribution is statistically indistinguishable from the golden sample.

* **Business Justification**: A brief explanation of why this specific metric is important for the overall goal of data fidelity and what business risk it mitigates.

* **Technical Specification**: A link to a design document, research paper, or technical notes outlining the specific libraries to use, key parameters, significance levels (thresholds), and any assumptions.

* **Fidelity Value Score (FVS)**:

- Impact (Metric Value): \`\`

- Confidence (Coverage Expansion): \`\`

- Effort: \`\`

- **FVS**: \[Auto-calculated]

* **Acceptance Criteria**:

- \[ ] The new metric is implemented as a new, self-contained test within the FidelityReporter codebase.

- \[ ] The metric is successfully integrated into the automated validation pipeline and runs on schedule.

- \[ ] The metric produces a clear Pass/Fail output and logs relevant diagnostic statistics (e.g., test statistic, p-value).

- \[ ] The "Total Scope" line on the Fidelity Score Burn-Up Chart is updated to include the "Metric Value" of this new metric upon completion.


#### **5.3. Tooling Recommendations: Supporting the IFR Workflow**

While the IFR workflow is a process, its efficiency can be greatly enhanced by the right tooling.

- **Data Validation Engine**: The FidelityReporter is the heart of the validation process. While it can be built as a custom application, leveraging established open-source data quality tools can accelerate its development and increase its robustness.

* **Great Expectations (GX)** is a leading open-source Python library designed specifically for data validation.<sup>37</sup> It provides a powerful framework for defining "Expectations" (which are directly analogous to our fidelity metrics), running validation against various data backends (files, databases, Spark), and automatically generating comprehensive "Data Docs" (which can serve as our validation reports).

* **dbt (Data Build Tool)**, especially when paired with the dbt-expectations package, offers a compelling alternative if the data being validated resides in a supported SQL data warehouse.<sup>37</sup> This approach allows for data transformations and data validation to be defined and executed within the same SQL-centric workflow.

- **Data Observability Platforms**: For more advanced, automated monitoring, alerting, and root cause analysis, commercial Data Observability platforms offer capabilities that go beyond standard validation.

* Tools like **Monte Carlo**, **Acceldata**, **Datadog**, or **Synq** provide end-to-end visibility into the entire data pipeline.<sup>27</sup> They can automatically profile data to learn its normal patterns, detect anomalies and data drift that might not be caught by fixed statistical tests, and provide powerful data lineage visualizations that can dramatically accelerate root cause analysis by showing exactly which upstream changes impacted a downstream asset. While building the\
  FidelityReporter is the core task of Epic 3, these platforms could augment its capabilities, particularly around real-time monitoring and advanced RCA.


#### **5.4. Secondary Insights: Finance and Regulatory Context**

The challenges faced in Epic 3 are not unique. Drawing parallels to high-stakes industries provides powerful external validation for the rigor of the proposed IFR workflow.

- **Quantitative Finance Case Studies**: The process of ensuring data fidelity for backtesting trading strategies, particularly in High-Frequency Trading (HFT), is a direct and compelling analogue to the RLX Co-Pilot's problem.<sup>43</sup> The profitability and risk management of an HFT firm depend entirely on the quality of the historical market data used to test its algorithms. Consequently, these firms have developed extremely rigorous processes for\
  **data cleansing** (e.g., identifying and correcting erroneous price ticks), **data normalization** (e.g., adjusting for stock splits and dividend payments), and ensuring data **completeness** and **granularity**.<sup>45</sup> The existence of sophisticated open-source tools like\
  hftbacktest, which are designed to simulate HFT strategies with high fidelity by accounting for latencies and order queue positions, underscores the maturity of this field.<sup>46</sup> The key lesson is that treating data fidelity as a first-class, mission-critical engineering problem, supported by dedicated processes and tools, is a proven strategy in industries where data errors have immediate and severe financial consequences.

- **Regulatory Frameworks (MiFID II)**: For organizations operating in or serving the financial sector, data quality is not just a best practice but a legal and regulatory mandate. Frameworks like Europe's **MiFID II** (Markets in Financial Instruments Directive II) impose strict and explicit requirements on financial firms for data quality, governance, validation, and record-keeping.<sup>47</sup> Regulations require firms to establish robust data governance frameworks, implement "data validation and cleansing processes," and maintain "clear data ownership and accountability".<sup>47</sup> Furthermore, they must be able to produce accurate transaction reports and demonstrate that they have a systematic process for ensuring best execution, all of which relies on high-quality, verifiable data. The implication for the RLX Co-Pilot project is profound: the IFR workflow is not just an agile methodology for efficient development; it is the implementation of a defensible, auditable system of controls. The documentation, triage records, work items, and convergence charts produced by this workflow serve as a comprehensive audit trail, proving that a systematic and rigorous process was followed to ensure the quality and integrity of the data product. This can be a powerful argument when communicating the importance and necessity of this work to senior leadership and compliance stakeholders.


#### **Works cited**

1. MLOps: Continuous delivery and automation pipelines in machine ..., accessed on August 1, 2025, <https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning>

2. Continuous Validation and Continuous Verification Process | Encord, accessed on August 1, 2025, <https://encord.com/blog/continuous-validation-machine-learning/>

3. MLOps Principles - Ml-ops.org, accessed on August 1, 2025, <https://ml-ops.org/content/mlops-principles>

4. (PDF) How DataOps Enables Continuous Data Delivery for Scalable MLOps Pipelines, accessed on August 1, 2025, <https://www.researchgate.net/publication/391321036_How_DataOps_Enables_Continuous_Data_Delivery_for_Scalable_MLOps_Pipelines>

5. The Role of MLOps and DataOps in Automating End-to-End Machine Learning Workflows, accessed on August 1, 2025, <https://www.researchgate.net/publication/391273993_The_Role_of_MLOps_and_DataOps_in_Automating_End-to-End_Machine_Learning_Workflows>

6. Feedback Loops: How to Do It the Agile Way - Businessmap, accessed on August 1, 2025, <https://businessmap.io/blog/feedback-loops>

7. Test-driven development (TDD) explained - CircleCI, accessed on August 1, 2025, <https://circleci.com/blog/test-driven-development-tdd/>

8. IMPROVE: Iterative Model Pipeline Refinement and Optimization Leveraging LLM Agents, accessed on August 1, 2025, <https://arxiv.org/html/2502.18530v1>

9. Scrum for Data Science, accessed on August 1, 2025, <https://www.datascience-pm.com/scrum/>

10. Scrum (software development) - Wikipedia, accessed on August 1, 2025, <https://en.wikipedia.org/wiki/Scrum_(software_development)>

11. Agile Management for Machine Learning: A Systematic Mapping Study - arXiv, accessed on August 1, 2025, <https://arxiv.org/html/2506.20759v1>

12. Agile MLOps: Designing AI Systems for Continuous Improvement | AWS Builder Center, accessed on August 1, 2025, <https://builder.aws.com/content/2kCvFqdcm0ubMxsz4qGirZsEepX/agile-mlops-designing-ai-systems-for-continuous-improvement>

13. What Is a Sprint in Agile? - Wrike, accessed on August 1, 2025, <https://www.wrike.com/project-management-guide/faq/what-is-a-sprint-in-agile/>

14. Mastering Sprint Planning for Agile Success - Product School, accessed on August 1, 2025, <https://productschool.com/blog/product-strategy/sprint-planning>

15. Agile Sprint Cycle: Definition, Execution, and Steps Explained - Designveloper, accessed on August 1, 2025, <https://www.designveloper.com/guide/agile-sprint-cycle/>

16. Scrum Sprints: Everything You Need to Know | Atlassian, accessed on August 1, 2025, <https://www.atlassian.com/agile/scrum/sprints>

17. Sprint Planning - Agile Alliance, accessed on August 1, 2025, <https://www.agilealliance.org/glossary/sprint-planning/>

18. 80+ User Story Examples and Templates \[2025] - Agilemania, accessed on August 1, 2025, <https://agilemania.com/user-story-examples>

19. User Stories | Examples and Template - Atlassian, accessed on August 1, 2025, <https://www.atlassian.com/agile/project-management/user-stories>

20. 100+ Free User Story Examples by Type and Use Case - Smartsheet, accessed on August 1, 2025, <https://www.smartsheet.com/content/user-story-examples>

21. How we prioritize feature requests, bug fixes, and security fixes ..., accessed on August 1, 2025, <https://success.atlassian.com/solution-resources/agile-and-devops-ado/product-specific-guidance/how-we-prioritize-feature-requests-bug-fixes-and-security-fixes>

22. How to Prioritize New Features vs Bug Fixes – Software Engineering ..., accessed on August 1, 2025, <https://sw-engineer.com/2015/03/31/how-to-prioritize-new-features-vs-bug-fixes/>

23. Bug fixes vs product features: what to prioritize - Shake, accessed on August 1, 2025, <https://www.shakebugs.com/blog/bug-fixes-vs-product-features/>

24. The Ultimate Guide to Prioritization - Airfocus, accessed on August 1, 2025, <https://airfocus.com/resources/guides/prioritization/>

25. Data Driven Scrum - Data Science PM, accessed on August 1, 2025, <https://www.datascience-pm.com/data-driven-scrum/>

26. Real-Time Data Validation on GCP with Apache Flink: Patterns, Scaling and Production Architecture | by Sendoa Moronta | Jul, 2025 | Dev Genius, accessed on August 1, 2025, <https://blog.devgenius.io/real-time-data-validation-on-gcp-with-apache-flink-patterns-scaling-and-production-architecture-0e84bb7871c8>

27. Top 13 Data Observability Tools of 2025: Key Features - Atlan, accessed on August 1, 2025, <https://atlan.com/know/data-observability-tools/>

28. Root Cause Analysis Guide for Data Engineers in 2024 - Atlan, accessed on August 1, 2025, <https://atlan.com/root-cause-analysis-guide-for-data-engineers/>

29. The Ultimate Customer Feedback Loop Guide - Thematic, accessed on August 1, 2025, <https://getthematic.com/insights/customer-feedback-loop-guide/>

30. What is a Burn Up Chart & How to Create One | Atlassian, accessed on August 1, 2025, <https://www.atlassian.com/agile/project-management/burn-up-chart>

31. What is burnup chart and how to use it? - Miro, accessed on August 1, 2025, <https://miro.com/agile/what-is-burnup-chart/>

32. Testing Trends in Test Reporting & Analytics | BrowserStack Docs, accessed on August 1, 2025, <https://www.browserstack.com/docs/test-reporting-and-analytics/features/testing-trends>

33. Data Visualization – How to Pick the Right Chart Type? - eazyBI, accessed on August 1, 2025, <https://eazybi.com/blog/data-visualization-and-chart-types>

34. Bug Report Template | Jira Templates - Atlassian, accessed on August 1, 2025, <https://www.atlassian.com/software/jira/templates/bug-report>

35. Make a Quality Bug Report: Step-By-Step Guide, Best Practices and ..., accessed on August 1, 2025, <https://testomat.io/blog/make-a-quality-bug-report-step-by-step-guide-best-practices-and-templates/>

36. How to write an Effective Bug Report | BrowserStack, accessed on August 1, 2025, <https://www.browserstack.com/guide/how-to-write-a-bug-report>

37. Great Expectations - Syntio, accessed on August 1, 2025, <https://www.syntio.net/en/labs-musings/great-expectations/>

38. Great Expectations - Deepnote docs, accessed on August 1, 2025, <https://deepnote.com/docs/great-expectations>

39. Great Expectations tutorial - Colab - Google, accessed on August 1, 2025, <https://colab.research.google.com/github/datarootsio/tutorial-great-expectations/blob/main/tutorial_great_expectations.ipynb>

40. Home | Great Expectations, accessed on August 1, 2025, <https://docs.greatexpectations.io/docs/home/>

41. New Package: dbt-expectations - Show and Tell - dbt Community ..., accessed on August 1, 2025, <https://discourse.getdbt.com/t/new-package-dbt-expectations/1771>

42. Monte Carlo, accessed on August 1, 2025, <https://www.montecarlodata.com/>

43. Synthetic Data in Investment Management | RPC - CFA Institute Research and Policy Center, accessed on August 1, 2025, <https://rpc.cfainstitute.org/research/reports/2025/synthetic-data-in-investment-management>

44. Quantitative Analysis (QA): What It Is and How It's Used in Finance - Investopedia, accessed on August 1, 2025, <https://www.investopedia.com/terms/q/quantitativeanalysis.asp>

45. Backtesting: Looking Back to Leap Forward: Backtesting Strategies ..., accessed on August 1, 2025, <https://www.fastercapital.com/content/Backtesting--Looking-Back-to-Leap-Forward--Backtesting-Strategies-in-High-Frequency-Trading.html>

46. nkaz001/hftbacktest: A high frequency trading and market making backtesting and trading bot in Python and Rust, which accounts for limit orders, queue positions, and latencies, utilizing full tick data for trades and order books, with real-world crypto market-making examples for Binance Futures and Bybit - GitHub, accessed on August 1, 2025, <https://github.com/nkaz001/hftbacktest>

47. Navigating MiFID II Compliance - Number Analytics, accessed on August 1, 2025, <https://www.numberanalytics.com/blog/navigating-mifid-ii-compliance-strategies>

48. Post-MiFID II / MiFIR - Review, Data Quality, Accuracy and Readiness | Issuer Services, accessed on August 1, 2025, <https://www.lsegissuerservices.com/spark-insights/8qrEDoKVfgkcahh5fSoGU7/post-mifid-ii-mifir-review-data-quality-accuracy-and-readiness>
