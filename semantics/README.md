# Semantics

Human-reviewed concept and relation definitions will live here as YAML.

Treat analytical semantics as revisable hypotheses, not authoritative truth.

The layers are:

- `entities/`: identity rules for things such as companies;
- `dimensions/`: scope and period axes that qualify a fact;
- `concepts/`: the meaning and evidence shape of directly disclosed facts;
- `operations/`: rules for values derived from disclosed facts;
- `tasks/`: dependency closure and answerability rules for an intent.

A gold case references these definitions and binds them to concrete values and evidence. It should
not copy their meanings. A semantic definition is promoted beyond `reviewed_for_case` only after it
has been checked against broader corpus variation.
