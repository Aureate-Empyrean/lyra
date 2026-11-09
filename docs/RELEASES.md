# Lyra releases and provenance

## Version control history

Development from 0.1.1 (commit `e849c73`) to 0.1.3 was not committed as it happened. Intermediate versions have no history and none was reconstructed. Commits and tags carry their true creation date, which is after deployment.

## 0.1.3

| | |
| --- | --- |
| Tag | `v0.1.3` (annotated, tag object `4fa3e5f9a82c78fa4c366f6a25bdb9b159803074`) |
| Baseline commit | `84f7f6511b40d62c3c184972d07911b613fc23b9`, created 2026-11-09 after deployment |
| Deployed image | `sha256:cc913a9bd7cbfbb9d73f19a646c7c1f82ca8202564d937edfc37870fae301b51` |
| Image config | `sha256:eff56bbecbd74f43d3c0fdb1ee81a218a69e90655155b49d8cd384b2abdad125` |
| Image built | 2026-11-09T08:43:40.473623453Z |
| Deployed | Exodus, 2026-11-09. The running container's image was read back on 2026-11-09 and matches the digest above |

### What has been demonstrated

Checked on 2026-11-09 from a clean clone of the tagged commit, against the image archive saved at release time.

- Of 16 non-compiled files in the image's `/app`, 6 are byte-identical to the tag and 10 differ only in line endings.
- The image was rebuilt with `deploy/Dockerfile`. Every file outside `/app` that is not a compiled `.pyc` is identical. Entrypoint, environment and user are the same.
- The unit suite passes on the clone: 15 passed.

### What has not been demonstrated

The build is **not reproducible to the digest**. Two rebuilds gave two different digests, sharing 7 of 11 layers with the deployed image.

- The deployed image was built from a Windows working tree, so 10 text files have CRLF line endings there and LF here.
- The deployed image holds 5 extra `.pyc` files under `/app`, copied from local test runs because `.dockerignore` does not exclude `__pycache__`. A clean checkout has none.
- The commit was made after the image was built. It records matching content, not the build's actual input.

## Conventions

Create the tag before deploying and build from a clean checkout of it. Record the commit and image digest in the deployment record. Do not move a published tag.
