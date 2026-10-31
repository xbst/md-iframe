"""Markdown extension that embeds HTML pages as auto-sizing iframes, designed for MkDocs/Zensical sites.

Usage in Markdown:
    ![Widget](path/to/page.html){ type=iframe style="min-height:40vh;width:100%" }

What it does: A TreeProcessor finds <img> tags whose ``type`` attribute is ``iframe`` and replaces them
with an ``<iframe>`` that loads the page.  ``type=application/pinout`` (the tag used by PinConnect's
original pinout-embed) is handled the same way.

Auto-height: an embedded page can post its content height to the parent page (PinConnect pinouts do
this when their theme stacks the connector list below the board on narrow screens).  A Postprocessor
adds one small listener per page that grows the matching iframe to fit.  It is backward compatible in
both directions: a page that never posts a height, or a page without the listener, simply keeps the
iframe's authored (min-)height.
"""

import re

from markdown import Extension
from markdown.treeprocessors import Treeprocessor
from markdown.postprocessors import Postprocessor
from xml.etree.ElementTree import Element

# Marker class on every embedded iframe; the listener uses it to scope itself.
EMBED_CLASS = "md-iframe"
# pinout-embed's marker class, kept on every iframe so existing user CSS still applies.
LEGACY_EMBED_CLASS = "pinconnect-embed"
ERROR_CLASS = "md-iframe-error"
LEGACY_ERROR_CLASS = "pinconnect-embed-error"

# Tags that convert, mapped to the label the missing-file error starts with.
# PinConnect's troubleshooting docs quote the "Pinout failed to load" text.
TYPE_LABELS = {
    "iframe": "Embed",
    "application/pinout": "Pinout",
}

# Carries the error label from the tag to the listener, so one script serves every type.
LABEL_ATTR = "data-md-iframe-label"

# A real embedded iframe in the page output.  Matching the tag (not just the
# class name) keeps prose and code samples that mention "md-iframe" from
# pulling in the listener: code blocks escape "<" as "&lt;".
_EMBED_RE = re.compile(
    r'<iframe\b[^>]*\bclass="[^"]*(?<![\w-])(?:%s|%s)(?![\w-])'
    % (re.escape(EMBED_CLASS), re.escape(LEGACY_EMBED_CLASS))
)

_SELECTOR = "iframe." + EMBED_CLASS + ",iframe." + LEGACY_EMBED_CLASS

# One listener per page.  Matches the posting iframe by window identity (so it
# works with several embeds on a page), sets the height on a positive value,
# and clears it on 0 so the iframe reverts to its authored height on wide
# screens.  A sanity cap ignores absurd values.  The height may come as
# ``mdIframeHeight`` or as PinConnect's ``pinconnectHeight``; newer pinouts
# send both in one message.
#
# The listener is added once per window, but the second block runs every time
# the script does: Material's and Zensical's instant navigation swap in a new
# page and run its scripts again without a reload, and that page's embeds still
# need checking.  Each iframe is marked once checked.
#
# The second block flags a broken embed instead of shipping a silently-blank
# iframe: a same-origin HEAD that returns 404 means the target file is missing
# (a typo, or the pinout was never generated), so the iframe is replaced with a
# visible error.  MkDocs reports this at build time; Zensical (and plain
# Markdown) do not, so this covers them at runtime.  Cross-origin embeds can't
# be checked (CORS) and are left untouched.
_LISTENER_SCRIPT = (
    "\n<script>\n"
    "(function(){\n"
    "  if(!window.__mdIframe){window.__mdIframe=true;\n"
    "  window.addEventListener('message',function(e){\n"
    "    var d=e.data;\n"
    "    if(!d||typeof d!=='object')return;\n"
    "    var h=d.mdIframeHeight;if(typeof h!=='number')h=d.pinconnectHeight;\n"
    "    if(typeof h!=='number'||h>20000)return;\n"
    "    var f=document.querySelectorAll('" + _SELECTOR + "');\n"
    "    for(var i=0;i<f.length;i++){\n"
    "      if(f[i].contentWindow===e.source){\n"
    "        var el=f[i];\n"
    "        if(el.dataset.mdIframeMinh===undefined)el.dataset.mdIframeMinh=el.style.minHeight||'';\n"
    "        if(h>0){\n"
    "          el.style.minHeight='0';\n"                     # content drives the height; drop the min-height floor
    "          el.style.height=h+'px';\n"
    "        }else{\n"
    "          el.style.minHeight=el.dataset.mdIframeMinh;\n"  # wide again: restore the authored min-height
    "          el.style.height='';\n"
    "        }\n"
    "        break;\n"
    "      }\n"
    "    }\n"
    "  });}\n"
    "  Array.prototype.forEach.call(document.querySelectorAll('" + _SELECTOR + "'),function(f){\n"
    "    if(f.dataset.mdIframeChecked)return;f.dataset.mdIframeChecked='1';\n"
    "    var src=f.getAttribute('src');if(!src)return;\n"
    "    fetch(src,{method:'HEAD'}).then(function(r){\n"
    "      if(r.status!==404)return;\n"
    "      var d=document.createElement('div');\n"
    "      d.className='" + ERROR_CLASS + " " + LEGACY_ERROR_CLASS + "';\n"
    "      d.style.cssText='display:flex;align-items:center;justify-content:center;"
    "box-sizing:border-box;padding:16px;width:100%;text-align:center;"
    "border:1px solid #d9534f;border-radius:8px;color:#d9534f;"
    "font-family:system-ui,sans-serif;font-size:14px;background:rgba(217,83,79,.06);';\n"
    "      d.style.minHeight=f.style.minHeight;\n"
    "      var label=f.getAttribute('" + LABEL_ATTR + "')||'" + TYPE_LABELS["iframe"] + "';\n"
    "      d.textContent='\\u26A0 '+label+' failed to load \\u2014 file not found: '+src;\n"
    "      f.replaceWith(d);\n"
    "    }).catch(function(){});\n"
    "  });\n"
    "})();\n"
    "</script>"
)


class IframeTreeprocessor(Treeprocessor):
    def run(self, root: Element) -> None:
        for img in root.iter("img"):
            label = TYPE_LABELS.get(img.get("type"))
            if label is None:
                continue
            src = img.get("src")
            if not src:
                continue

            # Preserve any inline style the author specified.  (The pinout animates
            # its own height when the list is toggled, and the auto-height listener
            # tracks that frame-by-frame — so the iframe must NOT have its own height
            # transition, or the two would fight.)
            style = img.get("style", "min-height:60vh;width:100%")

            # Convert <img> → <iframe>
            img.tag = "iframe"
            img.set("src", src)
            img.set("style", style)
            img.set("frameborder", "0")
            img.set("loading", "lazy")
            img.set("allowfullscreen", "true")
            img.set(LABEL_ATTR, label)

            # Marker classes (kept alongside any author-supplied class) so the
            # auto-height listener can find and resize this iframe.
            markers = f"{EMBED_CLASS} {LEGACY_EMBED_CLASS}"
            existing = img.get("class")
            img.set("class", f"{existing} {markers}".strip() if existing else markers)

            # iframes have no alt; give it a title (tooltip / accessible name).
            # Prefer an explicit Markdown image title -- ![alt](src "title") --
            # and only fall back to the alt text, instead of always clobbering
            # the title with alt.
            if not img.get("title"):
                alt = img.get("alt", "")
                if alt:
                    img.set("title", alt)
            if "alt" in img.attrib:
                del img.attrib["alt"]

            # Clean up image-only attributes
            for attr in ("type",):
                if attr in img.attrib:
                    del img.attrib[attr]

            # iframes need closing tags; ensure there's text content
            # (empty string prevents self-closing <iframe/>)
            img.text = ""


class IframeHeightPostprocessor(Postprocessor):
    """Append the auto-height listener once, if the page has any embedded iframe."""

    def run(self, text: str) -> str:
        if _EMBED_RE.search(text):
            return text + _LISTENER_SCRIPT
        return text


class IframeExtension(Extension):
    def extendMarkdown(self, md):
        # Negative priority so this runs AFTER the host's relative-path pass.
        # MkDocs' `relpath` treeprocessor (priority 0) rewrites relative links,
        # but only on <a href>/<img src>. If we converted <img> to <iframe>
        # first (as at priority 1), relpath would skip the iframe and its
        # relative src would 404 under use_directory_urls (the default). Running
        # later lets relpath resolve the <img src>, which we then carry onto the
        # iframe. Zensical rewrites every element's src regardless of order, so
        # it is unaffected either way.
        #
        # The names are fixed, so listing both `md_iframe` and `pinout_embed`
        # re-registers the same processors instead of adding a second listener.
        md.treeprocessors.register(
            IframeTreeprocessor(md), "md_iframe", -5
        )
        md.postprocessors.register(
            IframeHeightPostprocessor(md), "md_iframe_height", 1
        )


def makeExtension(**kwargs):
    return IframeExtension(**kwargs)
