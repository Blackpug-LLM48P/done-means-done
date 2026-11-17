# Pre-collection compatibility normalization

This formatting-only repair occurred before any runner collection began. The 70 block-header prefixes changed from `Lnn｜` to `[Lnn] ｜`; all other record bytes, including the descriptive draft label, remain unchanged. Metadata now identifies the draft by block ID `L70` and records the normalized record size and hash. There is no semantic or answer change. `KEY.md` was not changed.

Exact originals are preserved in `RECORD.authored.txt` and `../metadata-04.authored.json`.

- Original record SHA-256: `7fbcecd8c62216157f7455874948e7f20968f579f506fe16db9ca51c69a01dd2`
- Normalized record SHA-256: `ee8baa22b6c8aee25f137b60d61a3a3c7c31df95716f3d3a495f58ac7876af49`
- Original metadata SHA-256: `a39cd7783262b0fe93b23ce7a2c7e02226fcd4e4b88c795ee952d6be56fb08c2`
- Normalized metadata SHA-256: `7d86c22b04f8f3a2fb6afdfcaa76ef2b4256f9c062855a87a93d409500d8be3a`
- Unchanged key SHA-256: `97051d00f81a3cd348045c1585d3d3b1d5898d0e6d92cf7fa3e7e5623b9f44bf`
