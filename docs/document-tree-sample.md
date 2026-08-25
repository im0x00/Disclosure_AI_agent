# DocumentTree compiler fixture

## Contract

One `DocumentTree` represents one disclosure and every XML/HTML artifact in its directory.

- `Node.kind` provides the shared document meaning.
- `Node.source_tag` and ordered attributes retain source-specific detail.
- Text and child nodes remain interleaved in source order.
- `Text.raw_value` keeps the source slice while `Text.display_value` normalizes whitespace.
- Unknown tags remain generic `element` nodes.
- Every node and text value carries XPath and UTF-8 byte ranges into the immutable raw file.
- Every artifact carries its source path, byte size, and SHA-256.
- PDF fallback files stay in the source registry; their paired viewer HTML builds the tree.

## Small fixture

- `doc_id`: `exchange_20230630800101`
- source: `corpus/raw/exchange/한화에어로스페이스/20230630800101/20230630800101.xml`
- source size: 7,300 bytes

This fixture checks that table markup, displayed values, raw values, and exact source ranges
survive inside the common recursive tree. The compiler does not create chunks, facts, or events.
