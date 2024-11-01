
.. warning:: This data class is at a **draft** maturity level and may change
    significantly in future releases. Maturity levels are described in 
    the :ref:`maturity-model`.
                      
                    
**Computational Definition**

The state of a molecule at a :ref:`Location`.

**Information Model**

Some Allele attributes are inherited from :ref:`Variation`.

.. list-table::
   :class: clean-wrap
   :header-rows: 1
   :align: left
   :widths: auto

   *  - Field
      - Type
      - Limits
      - Description
   *  - id
      - string
      - 0..1
      - The 'logical' identifier of the entity in the system of record, e.g. a UUID. This 'id' is  unique within a given system. The identified entity may have a different 'id' in a different  system, or may refer to an 'id' for the shared concept in another system (e.g. a CURIE).
   *  - label
      - string
      - 0..1
      - A primary label for the entity.
   *  - description
      - string
      - 0..1
      - A free-text description of the entity.
   *  - extensions
      - :ref:`Extension`
      - 0..m
      - 
   *  - type
      - string
      - 0..1
      - MUST be "Allele"
   *  - digest
      - string
      - 0..1
      - A sha512t24u digest created using the VRS Computed Identifier algorithm.
   *  - expressions
      - :ref:`Expression`
      - 0..m
      - 
   *  - location
      - :ref:`IRI` | :ref:`Location`
      - 1..1
      - The location of the Allele
   *  - state
      - :ref:`SequenceExpression`
      - 1..1
      - An expression of the sequence state
