# Vendored eval corpus — DeFiVulnLabs

**Source:** [SunWeb3Sec/DeFiVulnLabs](https://github.com/SunWeb3Sec/DeFiVulnLabs)
— a Web3 Solidity security training set (XREX). Each file is a self-contained
Foundry reproduction of one vulnerability class, encoded in the file name.

**Vendored:** 2026-07-20 — 53 of 57 upstream files.

## Why vendored

These reproductions are the held-out evaluation corpus. Committing them lets
`make eval` and the detector benchmark run **cold** — on a fresh clone, with no
access to the private `security-lab` engine. The numbers a reviewer reproduces
are then the same numbers the README claims, on the same public corpus.

## License

Every vendored file carries an `SPDX-License-Identifier: MIT` header and is
redistributed here under that per-file MIT grant, with attribution to the
upstream authors.

**4 upstream files are deliberately excluded** — they carry
`SPDX-License-Identifier: UNLICENSED` (no redistribution grant):
`interface.sol`, `NFTMint_exposedMetadata.sol`, `SenseFinance_exp.sol`,
`UniswapV3ETHRefundExploit.sol`. None map to a detector class, so excluding them
does not change the recall denominator (covered cases stay 34).

```
MIT License

Copyright (c) SunWeb3Sec and DeFiVulnLabs contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
