# **\>\_CERNAL: Compiler-like Engine for RNA Logic**

### **Motivation for our work:** 

It has long been a target of synthetic biology to create reliable, programmable and versatile intracellular logic. It would allow for complex and context specific systems, accelerating research, R\&D and creating therapeutic opportunities.  \[(Singh, 2014), (Liu et al., 2021\)\]

Logic is the first step in the creation of a complex system. It is based on the predictability and consistency of interactions, designing specific outcomes from defined conditions through logic gates. In electrical engineering for example, binary logic is commonly used \- and a basic circuit that displays the versatility and applicability of logic is the classic “Full-Adder” circuit.   
There were works that tried to create logic and circuits in biological cells, through the use of Transcription Factors (TFs). But they struggle with adaptability and modifications, and their characterization requires a lot of chassis-specific lab work \[(Armstrong & Isalan, 2024\)\].  
What if we had a platform to create intracellular circuits, that are widely applicable and are less labour intensive – We propose CERNAL, a biological compiler for the creation of intracellular circuits.

### **Introduction:**

The major difficulties in developing synthetic biology circuits that we identified were; 1\) the insufficient control gene regulation methods provide, 2\) the host dependency of these methods and 3\) their reliance on external signals \[(Costello & Badran, 2020\)\].

Gene regulation methods, such as ((info:Tet-ON/OFF or IPTG inducible promoters)), are inherently limited by their reliance on fixed, engineered protein-DNA interactions that are characterized as “Parts”. These parts are often viewed as a solution for creating regulatory networks and circuits, but their characterization requires extensive empirical testing \- This creates host dependency issues, as parts optimized for specific organisms can exhibit different behavior in another. These shifts demand additional optimizations and ultimately limit the development of complex circuits \[(Vazquez-Vilar et al., 2023\)\] \[(Cardinale & Arkin, 2012\)\].

Additionally, These methods act like static, "context-blind" switches flipped by an outsider, failing to account for the breathtaking complexity of a living cell. This reliance on external, artificial triggers means these switches cannot "sense" the nuanced difference between a diseased cell and its healthy neighbor, or distinguish a toxic environment from a safe one. By ignoring the cell’s internal transcriptomic state, these systems lack the molecular precision required for complex tasks, inevitably causing side effects by activating “off-target” and “off-time” \[(Galvan et al., 2024\)\].

### **The CERNAL Platform:**

**CERNAL** (Compiler-like Engine for RNA Logic) is a computational pipeline designed to bridge the gap between high-throughput ((info:transcriptomic)) data and functional synthetic gene circuits. The platform automates the design of conditional expression mechanisms by allowing researchers to define their desired activation conditions as constraints. By analyzing raw RNA-seq data against these requirements, CERNAL generates a genetic blueprint for a plasmid, integrating a logic circuit and payload, while optimizing for a high signal-to-noise ratio to prevent the "leaky" expression often found in static systems.

We tackle the difficulties previously identified through the use of smart, context aware RNA-switches. These switches would provide a way to interpret the cell’s own internal data and translate it into a precise, logic-gated response to make a biological circuit. Furthermore, by utilizing RNA these switches can be organism agnostic. Unlike protein-based controls that are hard to model and effectively “organism-specific”, RNA-RNA interactions follow universal thermodynamic laws. Whether it’s a microbe, a plant, or a human neuron, the physics of RNA folding remain constant. **If a cell produces RNA, we can read its signature, and we can code for it.**

Our CERNAL model operates through four integrated modules:

1. **Differential Expression & Pattern Recognition:** this module identifies state-specific mRNA fingerprints by analyzing differential RNA-seq datasets (e.g., healthy vs. diseased tissue). It then isolates “trigger RNAs” \- optimal molecular markers selected for their high sensitivity and specificity \- to reliably represent these transcriptomic patterns.  
2. **Logic Circuit Synthesis:** Based on the identified triggers, the system compiles a suite of RNA-based switches, such as Toehold Switches and CRISPR-guide RNAs, to construct complex Boolean logic circuits (AND, OR, NOT).  
3. **Biophysical Modeling & Robustness Analysis:** Utilizing RNA folding algorithms and binding energy predictions, the model simulates the interactions between triggers and switches. We specifically address the "noise" inherent in biological systems, optimizing for the highest signal-to-noise ratio, mitigating the "leaky" expression profiles often found in static systems.  
4. **Heuristic Optimization**: The pipeline implements a selection heuristic to choose the biological components that are the "best-fit" for the user's desired action. It balances the theoretical effectiveness of a logic gate with its predicted robustness in the cellular environment, outputting the most promising plasmid candidates.

### **From In-Silico to In-Vivo: Validation and Case Studies** 

To demonstrate the versatility of our compiler, the bio-team has validated the pipeline across multiple use cases and organisms; precision targeted therapy in mammalian cells, and biosensors in both prokaryotes and eukaryotes.

\[§Selector element for case study\]

### **Proof of Concept I: Precision Targeted Therapy for Endometriosis**

Endometriosis is a chronic inflammatory disease affecting approximately 6–10% of women of reproductive age worldwide. Current therapeutic efficacy is often limited by the condition's uncertain etiology and diverse clinical presentations, which range from local gynecologic lesions to systemic inflammatory disorders. Patients are typically restricted to a combination of surgical removal of endometriotic foci and hormonal suppression; however, these pharmacological treatments frequently result in poor compliance due to intolerable side effects. Furthermore, surgical intervention alone carries a high risk of recurrence, with an estimated 50% of women requiring a subsequent procedure within five years if long-term medication control is not maintained. These repeated interventions can lead to cumulative organ damage and loss of function, underscoring the urgent need for therapeutic strategies that achieve enduring symptom relief and fertility preservation while addressing the systemic impacts of the disease \[(Chen et al., 2023\)\].

**Implementing CERNAL** to ingest RNA-seq data from ectopic lesions and healthy tissue allows the identification of a unique, multidimensional transcriptomic signature. And by selecting a combination of RNA triggers co-expressed exclusively in the lesion, our pipeline designs a cell-specific boolean logic circuit.

**The Molecular Circuit** employs synthetic RNA regulators, such as toehold switches, that sequester the translation of a therapeutic payload in a "closed" state. For example a simple “AND” logic would be sensitive to a specific trigger RNAs;

* **In healthy tissue:** The absence of the specific trigger RNAs prevents switch activation, leaving the therapeutic payload silenced.

* **In target lesions:** The presence of the trigger RNAs facilitates the unfolding of the switch, enabling the translation of a pro-apoptotic or cytotoxic payload.

Our logic-gated approach ensures that the therapeutic compound is expressed "if and only if" the complex pathological environment is detected. This absolute molecular specificity allows us to induce localized cell death within the lesions while leaving healthy uterine and pelvic tissues entirely untouched.Thus, our platform offers a path toward a minimally invasive solution that tackles the root cause of pain without the debilitating systemic damage caused by hormonal treatments or the trauma of repeated surgeries.

### **Proof of Concept II: On-Site Detection of PFAS**

Per- and polyfluoroalkyl substances (PFAS) are synthetic "forever chemicals" with high environmental persistence \[(Walker & Milligan, 2025\)\]. Chronic exposure is linked to significant health risks \[(Fenton et al., 2020\)\], yet current detection and tracking of PFAS contamination remains a bottleneck \- tethered to centralized laboratory equipment like liquid chromatography-mass spectrometry (LC-MS) \[(Chugh et al., 2026\)\]. Making rapid, frequent, and wide-scale on-site environmental monitoring economically and logistically impossible for most communities.

We applied **CERNAL** here to engineer a portable, low-cost microbial biosensor using both yeast and E. coli. The pipeline analyzes the host's condition-specific transcriptome to extract a unique RNA fingerprint, and outputs a logic circuit. This circuit is then encoded on a plasmid to express a detectable payload.

**The Circuit** utilizes multiple boolean logic gates to ensure that a reporter protein (such as a fluorescent marker) is expressed only when the precise combination of PFAS-induced RNAs is present. By compounding these gates, the system filters out biological "noise" and non-specific stress responses, providing a high-fidelity visual readout suitable for field-based environmental monitoring.

### **CERNAL: A Modular Framework with integrated DBTL cycle**

The strength of the CERNAL platform lies in its orthogonal, decoupled architecture. The detection of endogenous inputs is functionally independent from the payload, transcending any single clinical application. This modularity-by-design allows the system to serve as a versatile biological engine for diverse applications \- from precision medicine and environmental biosensing to agricultural diagnostics and industrial bioprocessing. 

**Design** stage in silico: 

* gates  
* Identification of optimal mRNAs to serve as triggers via RNA-seq  
* Selection of trigger sequences from the complete mRNA

**Build** stage:

* Gibson to construct plasmids  
* 

**Test** with cell assays:

* Validation of the resulted plasmid in cells  
* CRISPR-Cas9 based gates validation through antibiotic switch assay ?  
* CRISPR-dCas validation through targeting cassette ?

**Learn** in a closed loop system:

* Provide data back to the computational lab  
* 

By providing a scalable, data-driven approach to intracellular computation, CERNAL facilitates the development of autonomous systems capable of high-fidelity intracellular sensing and executing complex responses.

### **Inspiration / why this project?**

We were inspired by last year's TAU project and thought to improve on its intracellular specificity ? ? ?

### 

### 

### **References:**

\[1\] Liu, L., Liu, P., Ga, L., & Ai, J. (2021). Advances in applications of Molecular Logic Gates. ACS Omega, 6(45), 30189–30204. [https://doi.org/10.1021/acsomega.1c02912](https://doi.org/10.1021/acsomega.1c02912)

\[2\] Armstrong, A., & Isalan, M. (2024). Engineering bacterial theranostics: from logic gates to in vivo applications. Frontiers in Bioengineering and Biotechnology, 12, 1437301\. [https://doi.org/10.3389/fbioe.2024.1437301](https://doi.org/10.3389/fbioe.2024.1437301)

\[3\] Singh, V. (2014). Recent advances and opportunities in synthetic logic gates engineering in living cells. Systems and Synthetic Biology, 8(4), 271–282. [https://doi.org/10.1007/s11693-014-9154-6](https://doi.org/10.1007/s11693-014-9154-6)

\[4\] Costello, A., & Badran, A. H. (2020). Synthetic Biological Circuits within an Orthogonal Central Dogma. Trends in Biotechnology, 39(1), 59–71. [https://doi.org/10.1016/j.tibtech.2020.05.013](https://doi.org/10.1016/j.tibtech.2020.05.013)

\[5\] Vazquez-Vilar, M., Selma, S., & Orzaez, D. (2023). The design of synthetic gene circuits in plants: new components, old challenges. Journal of Experimental Botany, 74(13), 3791–3805. [https://doi.org/10.1093/jxb/erad167](https://doi.org/10.1093/jxb/erad167)

\[6\] Cardinale, S., & Arkin, A. P. (2012). Contextualizing context for synthetic biology – identifying causes of failure of synthetic biological systems. Biotechnology Journal, 7(7), 856–866. [https://doi.org/10.1002/biot.201200085](https://doi.org/10.1002/biot.201200085)

\[7\] Galvan, S., Teixeira, A. P., & Fussenegger, M. (2024). Enhancing cell‐based therapies with synthetic gene circuits responsive to molecular stimuli. Biotechnology and Bioengineering, 121(10), 2987–3000. [https://doi.org/10.1002/bit.28770](https://doi.org/10.1002/bit.28770)

\[8\] Chen, L., Lo, W., Huang, H., & Wu, H. (2023). A Lifelong Impact on Endometriosis: Pathophysiology and pharmacological treatment. International Journal of Molecular Sciences, 24(8), 7503\. [https://doi.org/10.3390/ijms24087503](https://doi.org/10.3390/ijms24087503)

\[9\] Walker, T., & Milligan, K. A. (2025). From persistence to progress: assessing per- and polyfluoroalkyl substances (PFAS) environmental impact and advances in photo-assisted fenton chemistry for remediation. *Frontiers in Environmental Chemistry*, *6*. [https://doi.org/10.3389/fenvc.2025.1591290](https://doi.org/10.3389/fenvc.2025.1591290) 

\[10\] Fenton, S. E., Ducatman, A., Boobis, A., DeWitt, J. C., Lau, C., Ng, C., Smith, J. S., & Roberts, S. M. (2020). Per- and Polyfluoroalkyl Substance Toxicity and Human Health Review: Current State of Knowledge and Strategies for Informing Future Research. *Environmental Toxicology and Chemistry*, *40*(3), 606–630. [https://doi.org/10.1002/etc.4890](https://doi.org/10.1002/etc.4890) 

\[11\] Chugh, V., Gaskin, P., & Zhang, W. (2026). Recent progress in current and emerging techniques for the detection of PFAS – the forever chemicals. *Sensors & Diagnostics*, *5*(3), 305–325. [https://doi.org/10.1039/d5sd00166h](https://doi.org/10.1039/d5sd00166h) 

