**Computational Definition**

A contextual value object for which a GA4GH computed identifier can be created.

**Information Model**

Some Ga4ghIdentifiableObject attributes are inherited from :ref:`gks.core:Entity`.

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
      - 
   *  - digest
      - string
      - 0..1
      - A sha512t24u digest created using the VRS Computed Identifier algorithm.
