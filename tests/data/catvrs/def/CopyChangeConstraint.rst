.. warning:: **Draft** — may change significantly in future releases. `Maturity Model </appendices/maturity_model.html>`_

**Computational Definition**

The relative assessment of the change in copies that members of this categorical variant satisfy.

**Information Model**

Some CopyChangeConstraint attributes are inherited from :ref:`Constraint`.

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
   *  - type
      -
      - string
      - 1..1
      - MUST be "CopyChangeConstraint"
   *  - copyChange
      -
      - string
      - 1..1
      - The relative assessment of the change in copies that members of this categorical variant satisfies.

**Used in:** :ref:`CategoricalCnv`
