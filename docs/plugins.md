# Plugin Development Guide

BuilderPulse supports three plugin types: **downloaders**, **sources**, and **channels**. Plugins are discovered via Python entry_points or registered dynamically at runtime.

## Plugin Protocols

### DownloaderPlugin

Handles downloading content from URLs.

```python
from typing import Any

class MyDownloader:
    name = "my-downloader"

    def can_handle(self, url: str) -> bool:
        """Return True if this plugin can handle the given URL."""
        return "example.com" in url

    def download(self, url: str, output_dir: str, **kwargs: Any) -> Any:
        """Download content from url into output_dir. Return path or result."""
        # Your download logic here
        output_path = f"{output_dir}/output.mp4"
        # ... download to output_path ...
        return output_path
```

### SourcePlugin

Provides a content source (feeds, APIs, scrapers).

```python
from typing import Any, List
from builderpulse.core.models import FeedItem

class MySource:
    name = "my-source"

    def fetch(self, **kwargs: Any) -> List[FeedItem]:
        """Fetch content items. kwargs may include days, limit, etc."""
        items = []
        # ... your fetch logic ...
        items.append(FeedItem(
            source_type="my_source",
            source_id="unique-id",
            url="https://example.com/item/1",
            title="Example Title",
            content="Item content...",
            author="Author Name",
            published_at="2026-01-01T00:00:00Z",
        ))
        return items
```

### ChannelPlugin

Delivers content to a destination (messaging, email, etc.).

```python
from typing import Any

class MyChannel:
    name = "my-channel"

    def deliver(self, content: Any, **kwargs: Any) -> Any:
        """Deliver content to the channel. kwargs may include title, etc."""
        title = kwargs.get("title", "BuilderPulse Digest")
        # ... your delivery logic ...
        return {"status": "sent", "channel": self.name}
```

## Registration via entry_points

Add your plugin to `pyproject.toml`:

```toml
[project.entry-points."builderpulse.downloaders"]
my-downloader = "my_package.downloaders:MyDownloader"

[project.entry-points."builderpulse.sources"]
my-source = "my_package.sources:MySource"

[project.entry-points."builderpulse.channels"]
my-channel = "my_package.channels:MyChannel"
```

After installing your package (`pip install -e .`), the plugin is automatically discovered on first access.

## Dynamic Registration

Register plugins at runtime without entry_points:

```python
from builderpulse.plugins.registry import PluginRegistry

# Create instances
downloader = MyDownloader()
source = MySource()
channel = MyChannel()

# Register on the global registry
registry = PluginRegistry()
registry.register("downloaders", downloader)
registry.register("sources", source)
registry.register("channels", channel)
```

## Custom Plugin Groups

Register entirely new plugin groups:

```python
from builderpulse.plugins.registry import PluginRegistry

# Register a new group (class-level, affects all instances)
PluginRegistry.register_group("transformers", "my_package.transformers")

# Now register plugins to the new group
registry = PluginRegistry()
registry.register("transformers", my_transformer_instance)
```

## Validation

Plugins are validated using `@runtime_checkable` Protocol checks. A plugin must have:

- A `name` attribute (str)
- All methods defined in the Protocol

If validation fails, the plugin is skipped with a warning logged. Other plugins continue loading.

## Error Handling

- One bad plugin never breaks others or the host
- Load errors are recorded and available via `registry.get_load_report()`
- Entry-point lookup failures are caught and logged

## Querying Plugins

```python
from builderpulse.plugins.registry import list_plugins, get_plugin

# List all plugins in a group
downloaders = list_plugins("downloaders")  # dict[str, instance]

# Get a specific plugin by name
dl = get_plugin("downloaders", "my-downloader")
if dl and dl.can_handle(url):
    result = dl.download(url, output_dir)
```
