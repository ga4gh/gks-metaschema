.. admonition:: Trial Use
    :class: note

    May change in future releases. `Maturity Model </appendices/maturity_model.html>`_

**Abstract Class** — not instantiated directly; concrete subclasses inherit its attributes.

**Computational Definition**

Constraints are used to construct an intensional semantics of categorical variant types.

**Information Model**


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
      - MUST be set to the name of the concrete Constraint subtype.

**Subclasses:** :ref:`AdjacencyConstraint`, :ref:`CopyChangeConstraint`, :ref:`CopyCountConstraint`, :ref:`DefiningAlleleConstraint`, :ref:`DefiningLocationConstraint`, :ref:`FeatureContextConstraint`, :ref:`FunctionConstraint`

**Used in:** :ref:`CategoricalVariant`
