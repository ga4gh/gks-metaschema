.. warning:: This data class is at a **draft** maturity level and may \
    change significantly in future releases. Maturity \
    levels are described in the :ref:`maturity-model`.

**Computational Definition**

A statement reporting a conclusion from a single study about whether a variant is associated with oncogenicity (positive or negative) - based on interpretation of the study's results.

**Information Model**

This class is defined as **all of** the following:

* :ref:`va.core:Statement`
* an object constraining ``proposition``, ``strength``, ``classification``, ``specifiedBy``, ``hasEvidenceLines``

