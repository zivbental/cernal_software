# **\>\_CERNAL: Compiler-like Engine for RNA Logic**

### **Introduction**

The fundamental bottleneck in biotechnology today is that while life is dynamic, our tools for controlling it remain static. 

Most current methods for gene regulation act like rigid, "context-blind" switches flipped by an outsider, failing to account for the breathtaking complexity of a living cell.   
These systems are inherently limited by their reliance on fixed, engineered protein-DNA interactions that are tied to the specific machinery of a single species. This creates a "language barrier" in synthetic biology: a switch designed for a lab-grown bacterium is often unreadable by a human cell or a plant tissue, posing a massive obstacle to scaling solutions across different organisms.

Beyond these technical hurdles lies a deeper design flaw: Contextual Blindness**.**   
Current tools depend on external, artificial triggers rather than the cell’s own internal world. They cannot "sense" the nuanced difference between a diseased cell and its healthy neighbor, or distinguish a toxic environment from a safe one. By ignoring the cell’s internal transcriptomic state, these systems lack the molecular precision required for complex tasks, leading to the systemic side effects and "off-target" damage that plague modern medicine and environmental interventions. 

To achieve true autonomy, we need a way to interpret the cell’s own internal data and translate it into a precise, logic-gated response that works in any biological “operating system”.

This is where RNA changes everything. Unlike protein-based controls that are “organism-specific”, RNA-RNA interactions follow universal thermodynamic laws. Whether it’s a microbe, a plant, or a human neuron, the physics of RNA folding remain constant.   
**If a cell produces RNA, we can read its signature, and we can code for it.**

### **The CERNAL Platform:**

CERNAL (Compiler-like Engine for RNA Logic) is a computational pipeline designed to bridge the gap between high-throughput transcriptomic data and functional synthetic gene circuits. The platform automates the design of conditional expression mechanisms, allowing researchers to input raw RNA-seq data from varying conditions to generate a genetic blueprint for a diagnostic or therapeutic plasmid.

Our CERNAL model operates through four integrated modules:

1. **Differential Expression & Pattern Recognition:** this module identifies state-specific mRNA fingerprints by analyzing differential RNA-seq datasets (e.g., healthy vs. diseased tissue). It then isolates “trigger RNAs” \- optimal molecular markers selected for their high sensitivity and specificity \- to reliably represent these transcriptomic patterns.  
2. **Logic Circuit Synthesis:** Based on the identified triggers, the system compiles a suite of RNA-based switches, such as Toehold Switches and CRISPR-guide RNAs, to construct complex Boolean logic circuits (AND, OR, NOT).  
3. **Biophysical Modeling & Robustness Analysis:** Utilizing RNA folding algorithms and binding energy predictions, the model simulates the interactions between triggers and switches. We specifically address the "noise" inherent in biological systems, optimizing for the highest signal-to-noise ratio, mitigating the "leaky" expression profiles often found in static systems.  
4. **Heuristic Optimization:** The pipeline implements a selection heuristic to choose the "best-fit" biological components. It balances the theoretical effectiveness of a logic gate with its predicted robustness in the cellular environment, outputting the most promising plasmid candidates.

### **From In-Silico to In-Vivo: Validation and Case Studies** 

To demonstrate the versatility of our compiler, the bio-team has validated the pipeline across multiple use cases and organisms; precision targeted therapy in mammalian cells, and biosensors in both prokaryotes and eukaryotes.

### **Proof of Concept I: Precision Targeted Therapy for Endometriosis**

Endometriosis is a chronic condition characterized by the growth of uterine-like tissue outside the uterus. Current standard-of-care treatments lack targeted therapeutic methods, and leave patients in a "therapeutic deadlock”. Patients are often forced to choose between systemic hormonal treatments \- which carry heavy side effects such as mood swings, bone density loss and infertility, or invasive surgeries to excise the growths. Even after surgical intervention, recurrence rates remain high, and chronic pelvic pain often persists, severely impacting the quality of life for millions of women worldwide. There is a requirement for a therapeutic intervention capable of eliminating lesions with molecular precision while maintaining endocrine integrity and sparing the surrounding healthy tissue.

**Implementing CERNAL** to ingest RNA-seq data from ectopic lesions and healthy tissue allows the identification of a unique, multidimensional transcriptomic signature. And by selecting a combination of RNA triggers co-expressed exclusively in the lesion, our pipeline designs a cell-specific boolean logic circuit.

**The Molecular Circuit** employs synthetic RNA regulators, such as toehold switches, that sequester the translation of a therapeutic payload in a "closed" state. For example a simple “AND” logic would be sensitive to a specific trigger RNAs;

* **In healthy tissue:** The absence of the specific trigger RNAs prevents switch activation, leaving the therapeutic payload silenced.  
* **In target lesions:** The presence of the trigger RNAs facilitates the unfolding of the switch, enabling the translation of a pro-apoptotic or cytotoxic payload.

Our logic-gated approach ensures that the therapeutic compound is expressed "if and only if" the complex pathological environment is detected. This absolute molecular specificity allows us to induce localized cell death within the lesions while leaving healthy uterine and pelvic tissues entirely untouched.Thus, our platform offers a path toward a minimally invasive solution that tackles the root cause of pain without the debilitating systemic damage caused by hormonal treatments or the trauma of repeated surgeries.

### **Proof of Concept II: On-Site Detection of PFAS**

Per- and polyfluoroalkyl substances (PFAS) are synthetic "forever chemicals" with high environmental persistence. Chronic exposure is linked to significant health risks, yet current detection and tracking of PFAS contamination remains a bottleneck \- tethered to centralized laboratory equipment like liquid chromatography-mass spectrometry (LC-MS). Making rapid, frequent, and wide-scale on-site environmental monitoring economically and logistically impossible for most communities.

**We Applied CERNAL** here to engineer a portable, low-cost microbial biosensor, utilizing both yeast and *E. coli*. The pipeline analyzes the transcriptomic response of the microbial host exposed to specific PFAS compounds, identifies the RNA fingerprint and outputs the logic circuit.

**The Circuit** utilizes multiple boolean logic gates to ensure that a reporter protein (such as a fluorescent marker) is expressed only when the precise combination of PFAS-induced RNAs is present. By compounding these gates, the system filters out biological "noise" and non-specific stress responses, providing a high-fidelity visual readout suitable for field-based environmental monitoring.

### **CERNAL: A Modular Framework**

The strength of the CERNAL platform lies in its orthogonal, decoupled architecture. The detection of endogenous inputs is functionally independent from the payload, transcending any single clinical application. This modularity-by-design allows the system to serve as a versatile biological engine for diverse applications \- from precision medicine and environmental biosensing to agricultural diagnostics and industrial bioprocessing.   
By providing a scalable, data-driven approach to intracellular computation, CERNAL facilitates the development of autonomous systems capable of high-fidelity intracellular sensing and executing complex responses.

### References:

