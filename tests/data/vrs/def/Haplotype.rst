.. warning:: This data class is at a **draft** maturity level and may \
    change significantly in future releases. Maturity \
    levels are described in the :ref:`maturity-model`.

**Computational Definition**

An ordered set of co-occurring :ref:`variants <Variation>` on the same molecule.

**GA4GH Digest**

.. list-table::
    :class: clean-wrap
    :header-rows: 1
    :align: left
    :widths: auto

    *  - Prefix
       - Inherent

    *  - HT
       - ['members', 'type']


**Information Model**

Some Haplotype attributes are inherited from :ref:`Variation`.

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
      - The 'logical' identifier of the entity in the system of record, e.g. a UUID. This 'id' is  unique within a given system. The identified entity may have a different 'id' in a different  system, or may refer to an 'id' for the shared concept in another system (e.g. a CURIE).
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
      - MUST be "Haplotype"
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
   *  - members
      - 
                        .. raw:: html

                            <span style="background-color: #B2DFEE; color: black; padding: 2px 6px; border: 1px solid black; border-radius: 3px; font-weight: bold; display: inline-block; margin-bottom: 5px;" title="Ordered">&#8595;</span>
      - :ref:`Adjacency` | :ref:`Allele` | :ref:`IRI`
      - 2..m
      - A list of :ref:`Alleles <Allele>` and :ref:`Adjacencies <Adjacency>` that comprise a Haplotype.  Members must share the same reference sequence as adjacent members. Alleles should not have overlapping or adjacent coordinates with neighboring Alleles. Neighboring alleles should be ordered  by ascending coordinates, unless represented on a DNA inversion (following an Adjacency with  end-defined adjoinedSequences), in which case they should be ordered in descending coordinates.  Sequence references MUST be consistent for all members between and including the end of one  Adjacency and the beginning of another.
