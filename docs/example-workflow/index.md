# Overview

This workflow develops and releases two products: `foundation-product` and
`dependent-product`. `dependent-product` imports a model from
`foundation-product`. The names describe their relationship; the same ownership
and release sequence applies to GKS products.

1. [Foundation Product](foundation-product.md): define a local model, generate
   artifacts, and prepare its release.
2. [Dependent Product](dependent-product.md): add the foundation product as a
   submodule, reference its model, generate artifacts, and prepare a release
   against a selected foundation branch or tag.
