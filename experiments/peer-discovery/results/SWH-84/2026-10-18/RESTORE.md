Download every repeat part ZIP and the case evidence archive into one directory. Extract the case evidence archive into a separate directory named case-evidence. Run the following command with Python 3 from the download directory:

```bash
python3 case-evidence/operator-scripts/restore_artifacts.py case-evidence/publication-parts.json . reconstructed
```

The script verifies each ZIP hash, part hash, reconstructed archive size and SHA256. Each reconstructed repeat tar archive contains publication-manifest.json with file hashes. The case evidence archive includes independent reconstruction receipts for all three repeats.
