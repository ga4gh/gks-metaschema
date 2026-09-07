.. note:: This data class is at a **trial use** maturity level and may \
    change in future releases. Maturity \
    levels are described in the :ref:`maturity-model`.

**Computational Definition**

A specialization of MappableConcept representing a single condition (disease, phenotype, or trait). Allowed conceptType values include: Condition, Phenotype, Disease, Trait, Absent.

**Information Model**

This class is defined as **all of** the following:

* :ref:`gkm.core:MappableConcept`
* an object constraining ``conceptType``
