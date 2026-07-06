# ADR-0001: Save Shift Package Format

## Status

Accepted

## Date

2026-07-06

---

## Context

Save Shift needs a reliable way to transfer save data between players while preserving metadata, detecting corruption, and supporting future features.

Using a plain ZIP archive would work for simple file transfer, but it provides no standardized metadata, versioning, or integrity verification.

---

## Decision

Save Shift packages use the `.sspkg` extension.

Internally, an `.sspkg` file is a ZIP archive containing:

```
manifest.json
checksums.json
files/
```

### manifest.json

Stores package metadata including:

- Package format version
- Game identifier
- Project name
- Package creation time (UTC)
- Package creator
- Save Shift version
- List of packaged files
- Future metadata

### checksums.json

Stores SHA-256 hashes for every packaged save file.

Checksums are used to verify package integrity before extraction.

### files/

Contains the original save files while preserving their directory structure.

---

## Consequences

### Advantages

- Versioned package format
- Self-describing archives
- Corruption detection
- Future extensibility
- Independent of any single game

### Disadvantages

- Slightly larger packages due to metadata
- Slightly longer package creation due to checksum generation
- Additional implementation complexity

---

## Future Considerations

Possible future additions include:

- Package thumbnails
- Compression settings
- Digital signatures
- Save notes
- Game version compatibility
- Package encryption
- Incremental backups