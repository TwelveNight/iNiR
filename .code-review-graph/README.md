# iNiR code review graph

Build and update from the repository root with `code-review-graph`:

```sh
code-review-graph build       # Full rebuild, required after language mapping changes
code-review-graph update      # Incremental update after source edits
code-review-graph status
code-review-graph visualize   # Regenerate graph.html after updates
```

`languages.toml` enables QML indexing using the bundled `qmljs` grammar,
following the configuration used by SekaiPop. It extracts JavaScript
functions, imports and calls from QML. Component instantiation, declarative
property bindings, signal wiring and QML module resolution are not
comprehensively modeled; inspect source when assessing these dependencies.

The database, HTML visualization and other generated data stay local and
are ignored by Git. Configuration and this README can be versioned.
This setup does not enable hooks, a background watcher or cloud embeddings.
