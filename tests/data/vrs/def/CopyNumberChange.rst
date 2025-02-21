.. warning:: This data class is at a **draft** maturity level and may \
    change significantly in future releases. Maturity \
    levels are described in the :ref:`maturity-model`.

**Computational Definition**

An assessment of the copy number of a :ref:`Location` or a :ref:`Gene` within a system (e.g. genome, cell, etc.) relative to a baseline ploidy.

**GA4GH Digest**

.. list-table::
    :class: clean-wrap
    :header-rows: 1
    :align: left
    :widths: auto

    *  - Prefix
       - Inherent

    *  - CX
       - ['copyChange', 'location', 'type']


**Information Model**

Some CopyNumberChange attributes are inherited from :ref:`CopyNumber`.

.. list-table::
   :class: clean-wrap
   :header-rows: 1
   :align: left
   :widths: auto

   *  - Field
      - Flags
      - Type
      - Limits
      - Description
   *  - id
      -
      - string
      - 0..1
      - The 'logical' identifier of the entity in the system of record, e.g. a UUID. This 'id' is unique within a given system. The identified entity may have a different 'id' in a different system, or may refer to an 'id' for the shared concept in another system (e.g. a CURIE).
   *  - label
      -
      - string
      - 0..1
      - A primary label for the entity.
   *  - description
      -
      - string
      - 0..1
      - A free-text description of the entity.
   *  - extensions
      -
                        .. raw:: html

                            <span style="background-color: #B2DFEE; color: black; padding: 2px 6px; border: 1px solid black; border-radius: 3px; font-weight: bold; display: inline-block; margin-bottom: 5px;" title="Ordered">&#8595;</span>
      - :ref:`Extension`
      - 0..m
      -
   *  - type
      -
      - string
      - 0..1
      - MUST be "CopyNumberChange"
   *  - digest
      -
      - string
      - 0..1
      - A sha512t24u digest created using the VRS Computed Identifier algorithm.
   *  - expressions
      -
                        .. raw:: html

                            <span style="background-color: #B2DFEE; color: black; padding: 2px 6px; border: 1px solid black; border-radius: 3px; font-weight: bold; display: inline-block; margin-bottom: 5px;" title="Unordered">&#8942;</span>
      - :ref:`Expression`
      - 0..m
      -
   *  - location
      -
      - :ref:`IRI` | :ref:`Location`
      - 1..1
      - A location for which the number of systemic copies is described.
   *  - copyChange
      -
      - string
      - 1..1
      - MUST be one of "efo:0030069" (complete genomic loss), "efo:0020073" (high-level loss), "efo:0030068" (low-level loss), "efo:0030067" (loss), "efo:0030064" (regional base ploidy), "efo:0030070" (gain), "efo:0030071" (low-level gain), "efo:0030072" (high-level gain).
