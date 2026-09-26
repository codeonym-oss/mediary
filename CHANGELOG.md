# Changelog

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
