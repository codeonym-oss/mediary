# Changelog

## [0.3.0](https://github.com/codeonym-oss/mediary/compare/v0.2.1...v0.3.0) (2026-09-29)


### Features

* add CQRS handler and behavior decorators ([#51](https://github.com/codeonym-oss/mediary/issues/51)) ([eab4768](https://github.com/codeonym-oss/mediary/commit/eab4768839181d89da2caafd7a25290393480c39))
* deprecate NotARequest, InvalidHandlerSignature and InvalidBehaviorSignature; use NotAMessage, InvalidHandler and InvalidBehavior ([#52](https://github.com/codeonym-oss/mediary/issues/52)) ([1dc3039](https://github.com/codeonym-oss/mediary/commit/1dc30390e6779d7c5aa0b37a731d95282b2fd7dc))
* deprecate passing Mediator.register's and RecordingMediator.sent_of/published_of/streamed_of's parameters by keyword; pass them positionally ([#52](https://github.com/codeonym-oss/mediary/issues/52)) ([1dc3039](https://github.com/codeonym-oss/mediary/commit/1dc30390e6779d7c5aa0b37a731d95282b2fd7dc))
* deprecate the .cls and .request_type attributes of errors; use .message_type ([#52](https://github.com/codeonym-oss/mediary/issues/52)) ([1dc3039](https://github.com/codeonym-oss/mediary/commit/1dc30390e6779d7c5aa0b37a731d95282b2fd7dc))
* run sync handlers on a worker thread ([#48](https://github.com/codeonym-oss/mediary/issues/48)) ([8d754b7](https://github.com/codeonym-oss/mediary/commit/8d754b7cfdca20ce2997d5057353ffc9a9a3ba6b))
* settle the public API before 1.0: Sender and Publisher protocols, NotificationCall for publish strategies, kinds= names checked, LoggingBehavior logs streams ([#52](https://github.com/codeonym-oss/mediary/issues/52)) ([1dc3039](https://github.com/codeonym-oss/mediary/commit/1dc30390e6779d7c5aa0b37a731d95282b2fd7dc))
* trace messages with OpenTelemetry, mediary[otel] ([#50](https://github.com/codeonym-oss/mediary/issues/50)) ([8df89b4](https://github.com/codeonym-oss/mediary/commit/8df89b4729de478c7e657dc3d1aad9f1939b77d7))


### Documentation

* move to Beta, with a stability policy ([#53](https://github.com/codeonym-oss/mediary/issues/53)) ([d592015](https://github.com/codeonym-oss/mediary/commit/d592015409dba33b663a60e4428ae7279b410c1d))

## [0.2.1](https://github.com/codeonym-oss/mediary/compare/v0.2.0...v0.2.1) (2026-09-26)


### Documentation

* move the docs site to Sphinx + Shibuya on Read the Docs ([#38](https://github.com/codeonym-oss/mediary/issues/38)) ([3082302](https://github.com/codeonym-oss/mediary/commit/3082302c8774a30cda9eb0a5e2a0818527240c16))

## [0.2.0](https://github.com/codeonym-oss/mediary/compare/v0.1.0...v0.2.0) (2026-09-26)


### Features

* add dishka and FastAPI integrations ([#14](https://github.com/codeonym-oss/mediary/issues/14)) ([45a9053](https://github.com/codeonym-oss/mediary/commit/45a9053ff1bec708a9ab0cec0a693a3b03531b4d))
* add stream requests ([#13](https://github.com/codeonym-oss/mediary/issues/13)) ([b6d4e45](https://github.com/codeonym-oss/mediary/commit/b6d4e458ba8dda48cd2faac0fd809e9be885d50c))
* run on trio through AnyIO with mediary[anyio] ([#16](https://github.com/codeonym-oss/mediary/issues/16)) ([6184c1c](https://github.com/codeonym-oss/mediary/commit/6184c1ccb8de40f6b25c9cca544bf2b62d91c66e))


### Documentation

* add documentation site ([#15](https://github.com/codeonym-oss/mediary/issues/15)) ([3bc6b23](https://github.com/codeonym-oss/mediary/commit/3bc6b23f8fb131d905ba42edab458c2a8dd1fe99))

## 0.1.0 (2026-09-26)


### Features

* add built-in logging, retry and timeout behaviors ([#9](https://github.com/codeonym-oss/mediary/issues/9)) ([ee53dd7](https://github.com/codeonym-oss/mediary/commit/ee53dd78ec91b8b872ab415402d0676dab0145d3))
* add RecordingMediator and a pytest plugin ([#11](https://github.com/codeonym-oss/mediary/issues/11)) ([19510e7](https://github.com/codeonym-oss/mediary/commit/19510e78244b212933c1498bb2d4cbcebdeb1041))
* add the CQRS extension pack on a public kinds API ([#10](https://github.com/codeonym-oss/mediary/issues/10)) ([750d425](https://github.com/codeonym-oss/mediary/commit/750d4252a3b8e3fd4376fbc844d86ed4a59757cb))
* discover requests and handlers by package scan ([#5](https://github.com/codeonym-oss/mediary/issues/5)) ([45e1a1f](https://github.com/codeonym-oss/mediary/commit/45e1a1fe3f26553f7d7887ff6bf5d47025ec5000))
* dispatch requests to handlers with a typed send ([#2](https://github.com/codeonym-oss/mediary/issues/2)) ([7d675bf](https://github.com/codeonym-oss/mediary/commit/7d675bfb1981c6eb5842523d3545df504fd5c025))
* publish notifications to all handlers with pluggable strategies ([#8](https://github.com/codeonym-oss/mediary/issues/8)) ([c076c0f](https://github.com/codeonym-oss/mediary/commit/c076c0fe1dbb91bf988b7420a31634fdd04a86f0))
* resolve handlers and dependencies through a pluggable resolver ([#6](https://github.com/codeonym-oss/mediary/issues/6)) ([2ff3d7d](https://github.com/codeonym-oss/mediary/commit/2ff3d7dcbd00ba9d103701f14769cea576a2a28e))
* retry only exceptions marked as retryable ([#28](https://github.com/codeonym-oss/mediary/issues/28)) ([1492fae](https://github.com/codeonym-oss/mediary/commit/1492faebf869a0c7a044988a471db13da90fa8d6))
* wrap handlers in targeted, ordered pipeline behaviors ([#7](https://github.com/codeonym-oss/mediary/issues/7)) ([5daaa3a](https://github.com/codeonym-oss/mediary/commit/5daaa3a0ff5a30e138336706365d59a2c3ef46ac))


### Documentation

* write the README and run its examples in CI ([#12](https://github.com/codeonym-oss/mediary/issues/12)) ([79b0a57](https://github.com/codeonym-oss/mediary/commit/79b0a57ea24c9c66744d3f8c594626cb8fae59ba))


### Build

* scaffold uv project with lint, typecheck, tests and CI ([#1](https://github.com/codeonym-oss/mediary/issues/1)) ([98b91a5](https://github.com/codeonym-oss/mediary/commit/98b91a5d86b6ec5d79533018cacb6c71a76ccdba))
