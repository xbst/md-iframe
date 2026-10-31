# md-iframe

A Python-Markdown extension for MkDocs and Zensical sites. It turns an image-style tag into an `<iframe>` that sizes itself to the embedded page and shows a visible error when the target file is missing.

```bash
pip install "git+https://github.com/xbst/md-iframe.git@master"
```

Enable it (with `attr_list`) in `mkdocs.yml`:

```yaml
markdown_extensions:
  - attr_list
  - md_iframe
```

Then embed a page:

```markdown
![Board pinout](board.pinout.html){ type=iframe style="min-height:60vh;width:100%" }
```

md-iframe replaces pinout-embed. Existing sites keep working unchanged: `{ type=application/pinout }` is still recognized, and `- pinout_embed` still loads this extension.
