# Chocolatey package: `netpulse`

Installs NetPulse from the official GitHub Release ZIP
(`NetPulse-win-x64-vX.Y.Z.zip`).

## Pack (local)

```powershell
cd pack/chocolatey/netpulse
choco pack
```

Produces `netpulse.0.1.0.nupkg`.

`choco pack` will succeed with the `REPLACE_ME` checksum placeholder. A real
install against GitHub Releases will not, until the SHA256 is filled in after
`v0.1.0` is published.

## Install from local nupkg

```powershell
choco install netpulse -y --source "'.;https://community.chocolatey.org/api/v2/'"
# or
choco install netpulse -y -s .
```

## Push to community feed (maintainers)

```powershell
choco push netpulse.0.1.0.nupkg --source https://push.chocolatey.org/ --api-key <YOUR_KEY>
```

Requires a [Chocolatey.org](https://community.chocolatey.org) account and
package moderation for first publish.

## Bumping a version

1. Set `VERSION` to `X.Y.Z` and update README release notes.
2. On Windows, run `.\scripts\publish-release.ps1` (wraps `build.bat` + zip + SHA256).
3. Publish GitHub release `vX.Y.Z` with `NetPulse-win-x64-vX.Y.Z.zip`.
4. Update `netpulse.nuspec` version and `releaseNotes`.
5. Update `$version` and the SHA256 value in `tools/chocolateyinstall.ps1`
   (replace `REPLACE_ME`).
6. Update `tools/VERIFICATION.txt`.
7. `choco pack` and push.
