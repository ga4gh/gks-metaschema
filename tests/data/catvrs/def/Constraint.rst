.. note:: This data class is at a **trial use** maturity level and may \
    change in future releases. Maturity \
    levels are described in the :ref:`maturity-model`.

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

This class must match **one of** the following:

* :ref:`DefiningAlleleConstraint`
* :ref:`DefiningLocationConstraint`
* :ref:`AdjacencyConstraint`
* :ref:`FeatureContextConstraint`
* :ref:`CopyCountConstraint`
* :ref:`CopyChangeConstraint`
* :ref:`FunctionConstraint`
