# Custom backends

The `StorageBackend` base class defines the interface for all storage operations. Subclass it to plug in custom storage (S3, database, git, shared drives).

## Interface

```python
class StorageBackend:
    def list_dates(self) -> list[str]: ...
    def list_versions(self, date: str) -> list[str]: ...
    def load_script(self, date: str, version: str) -> ScriptSections: ...
    def load_data(self, date: str) -> pd.DataFrame | None: ...
    def load_plot(self, date: str, version: str) -> bytes | None: ...
    def save_version(self, date: str, sections: ScriptSections) -> str: ...
    def run_preview(self, sections, inject_vars=None) -> RunResult: ...
    def run_full(self, sections, inject_vars=None) -> RunResult: ...
    def starter_template(self, date: str) -> ScriptSections: ...
```

You only need to override the methods you want to customize. The base class provides sensible defaults (empty lists, None, NotImplementedError for save).

## FileSystemBackend

The default backend. Expects this directory layout:

```
base_dir/
  data/     data_{YYYYMMDD}.csv|parquet
  scripts/  script_{YYYYMMDD}_v{N}.py
  plots/    plot_{YYYYMMDD}_v{N}.png
```

Customizable via regex patterns:

```python
backend = FileSystemBackend(
    base_dir="./my_project",
    data_pattern=r"data_(?P<date>\d{8})\.(csv|parquet)$",
    script_pattern=r"script_(?P<date>\d{8})_v(?P<version>\d+)\.py$",
    plot_pattern=r"plot_(?P<date>\d{8})_v(?P<version>\d+)\.png$",
)
```

## Auto-discovery

Scan a parent directory for sub-plots:

```python
backends = FileSystemBackend.discover("./all_plots")
# Returns {"plot1": FileSystemBackend, "plot2": FileSystemBackend, ...}

gallery = Gallery(backends=backends)
```

Any subdirectory containing `data/` or `scripts/` is treated as a plot.

## Custom starter template

Override what new scripts look like:

```python
def my_template(date, base_dir):
    return ScriptSections(
        configurator=f'title: str = "{date}"',
        code="import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n# your code here",
    )

backend = FileSystemBackend("./my_project", starter_template_fn=my_template)
```

## Example: S3-backed storage

```python
class S3Backend(StorageBackend):
    def __init__(self, bucket, prefix):
        self.bucket = bucket
        self.prefix = prefix

    def list_dates(self):
        # List S3 prefixes under self.prefix/data/
        ...

    def load_script(self, date, version):
        key = f"{self.prefix}/scripts/script_{date}_v{version}.py"
        text = s3_client.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode()
        return ScriptSections.from_text(text)

    def save_version(self, date, sections):
        # Upload to S3
        ...
```

## API Reference

::: gallery_viewer.StorageBackend

::: gallery_viewer.FileSystemBackend
