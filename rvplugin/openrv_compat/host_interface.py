# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sam Richards
"""
OpenRV host interface: replaces XStudioHostInterface.

Implements the same public API (load_media, replace_current_media,
compare_with_current_media, append_media, preview_media) using
rv.commands.

Key OpenRV API notes
--------------------
* addSource(path)         — void; does NOT return a node.
* addSourceVerbose([path])— returns the RVFileSource node name created
                            (e.g. "sourceGroup000003_source").
* nodeGroup(node)         — returns the parent source group of a node
                            (e.g. "sourceGroup000003"). Source groups are
                            top-level and can be passed to setViewNode.
* setViewNode(group)      — switches the viewer to that source group.
* deleteNode(group)       — removes a node (and its sub-graph) from the
                            session.  There is no deleteSource() in the
                            Python bindings.
* setSourceMedia(fsNode, [path], tag) — replace media in an existing
                            RVFileSource node without creating a new
                            source group (used for efficient preview).
* sources()               — returns tuples of (filename, startFrame, …)
                            NOT node names; use nodesOfType("RVSourceGroup")
                            to enumerate source group nodes.
* newNode(type, name)     — creates a node of the given type; returns the
                            generated node name string.
* setNodeInputs(node, [inputs]) — wire source groups as inputs to a stack.
* nodesOfType(type)       — list all node names of the given type.
* sendInternalEvent(name, content) — fire a named event (e.g. "key-down--f6"
                            triggers the Wipes toggle).

Sequence path conversion
------------------------
XStudioHostInterface uses xStudio's brace-padding format
(/dir/base{:04d}.ext=1001-1050).  OpenRV expects printf-style without a
frame range (/dir/base.%04d.ext) and auto-discovers the frames from disk.
We convert via _to_openrv_path() below.

Usage
-----
    plugin = FilesystemBrowserPlugin(mode)
    plugin.host = OpenRVHostInterface(mode, plugin)
"""

try:
    import rv.commands as _rvc
    _RV_AVAILABLE = True
except ImportError:
    _rvc = None
    _RV_AVAILABLE = False

try:
    import fileseq as _fileseq
    _FILESEQ = True
except ImportError:
    _fileseq = None
    _FILESEQ = False


def _to_openrv_path(path):
    """
    Convert a fileseq sequence string to the printf path OpenRV expects.

    OpenRV auto-discovers the frame range from disk when given a printf
    path, so we omit the frame range.  Including it caused problems with
    newer fileseq versions that zero-pad ranges ("02500-02699") which
    some OpenRV builds do not parse correctly.

    Single files and movie files pass through unchanged.
    """
    if not _FILESEQ:
        return path
    try:
        seq = _fileseq.FileSequence(path)
        if len(seq) <= 1:
            return path
        pad = seq.padding() or "@@@@"
        pad_len = pad.count('#') * 4 + pad.count('@')
        fmt = f"%0{pad_len}d" if pad_len > 0 else "%d"
        return f"{seq.dirname()}{seq.basename()}{fmt}{seq.extension()}"
    except Exception:
        return path


def _view_node():
    """Return the current view node name, or None."""
    if not _RV_AVAILABLE:
        return None
    try:
        return _rvc.viewNode()
    except Exception:
        return None


def _add_source(rv_path):
    """
    Add a new source and return (file_source_node, source_group_node).

    Uses addSourceVerbose (returns the RVFileSource node) rather than
    addSource (void) so that we can obtain a node name for setViewNode
    and deleteNode.
    """
    try:
        file_source = _rvc.addSourceVerbose([rv_path])
        if file_source:
            group = _rvc.nodeGroup(file_source)
            return file_source, group
    except Exception as e:
        print(f"OpenRV _add_source error ({rv_path!r}): {e}")
    return None, None


def _delete_source_group(group):
    """Delete a source group from the session."""
    if not group:
        return
    try:
        _rvc.deleteNode(group)
    except Exception as e:
        print(f"OpenRV _delete_source_group error ({group!r}): {e}")


class OpenRVHostInterface:
    """
    OpenRV implementation of the media-loading host interface.
    Mirrors the public methods of XStudioHostInterface exactly.
    """

    def __init__(self, connection, plugin):
        self.connection = connection   # FilesystemBrowserMode instance
        self.plugin = plugin
        # Preview state
        self._preview_fs = None        # RVFileSource node of preview source
        self._preview_group = None     # Source group node of preview source
        self._pre_preview_view = None  # View to restore when preview ends
        self._preview_path = None      # Original path of current preview clip
        # Compare state
        self._compare_stack = None     # RVStackGroup node name for wipe compare
        # Real-view tracking: set only by load/replace, never by preview.
        # This is the authoritative "what was genuinely being watched" node.
        self._last_real_view = None

    # ------------------------------------------------------------------
    # Public API (same signatures as XStudioHostInterface)
    # ------------------------------------------------------------------

    def load_media(self, path):
        """Add a file or sequence, switch to it, and discard any preview."""
        if not _RV_AVAILABLE:
            print(f"OpenRV not available; would load: {path}")
            return
        try:
            self._clear_preview(switch_view=False)
            _fs, group = _add_source(_to_openrv_path(path))
            if group:
                self._last_real_view = group
                _rvc.setViewNode(group)
        except Exception as e:
            print(f"OpenRVHostInterface.load_media error: {e}")

    def replace_current_media(self, path):
        """Replace the currently viewed source with new media."""
        if not _RV_AVAILABLE:
            return
        try:
            self._clear_preview(switch_view=False)
            old_group = _view_node()
            _fs, group = _add_source(_to_openrv_path(path))
            if group:
                self._last_real_view = group
                _rvc.setViewNode(group)
            if old_group and old_group != group:
                _delete_source_group(old_group)
        except Exception as e:
            print(f"OpenRVHostInterface.replace_current_media error: {e}")

    def compare_with_current_media(self, path):
        """
        Compare the last real (non-preview) source with path using Wipes.

        Primary source: _last_real_view (set by load/replace only, never by
        preview) so that previewing a clip first does not corrupt the primary.
        Falls back to _pre_preview_view when in preview mode, then _view_node().

        Secondary source: if the current preview clip IS the requested compare
        path, the preview source is promoted in-place (no duplicate entry in
        the session).  Otherwise the preview is cleared and a new source is
        added.
        """
        if not _RV_AVAILABLE:
            return
        try:
            rv_path = _to_openrv_path(path)

            # Determine the primary (real) source to compare against.
            if self._last_real_view:
                primary = self._last_real_view
            elif self._preview_fs is not None and self._pre_preview_view:
                primary = self._pre_preview_view
            else:
                primary = _view_node()

            # Determine the secondary (compare) source without creating duplicates.
            if self._preview_fs is not None and self._preview_path == path:
                # The preview slot already holds this exact clip — promote it.
                new_group = self._preview_group
                self._preview_fs = None
                self._preview_group = None
                self._preview_path = None
                self._pre_preview_view = None
            else:
                # Different path (or no preview): clear any stale preview first
                # so we don't leave an orphan source in the session.
                self._clear_preview(switch_view=False)
                _fs, new_group = _add_source(rv_path)
                if not new_group:
                    return

            # Reuse the compare stack if it still exists in the session.
            existing_stacks = set(_rvc.nodesOfType("RVStackGroup"))
            if self._compare_stack and self._compare_stack in existing_stacks:
                stack = self._compare_stack
            else:
                stack = _rvc.newNode("RVStackGroup", "FilesystemBrowserCompare")
                self._compare_stack = stack

            inputs = [primary, new_group] if primary else [new_group]
            _rvc.setNodeInputs(stack, inputs)
            _rvc.setViewNode(stack)

            try:
                _rvc.sendInternalEvent("key-down--f6", "")
            except Exception:
                pass
        except Exception as e:
            print(f"OpenRVHostInterface.compare_with_current_media error: {e}")

    def append_media(self, path):
        """Add media to the session without changing the current view."""
        if not _RV_AVAILABLE:
            return
        try:
            _add_source(_to_openrv_path(path))
        except Exception as e:
            print(f"OpenRVHostInterface.append_media error: {e}")

    def preview_media(self, path):
        """
        Temporarily show media for a quick look.

        On first call: saves the current view, adds a preview source,
        switches to it.

        On subsequent calls: replaces the media inside the existing
        preview source group (setSourceMedia) rather than adding a new
        source, so the session doesn't accumulate one source per hover.

        load_media() discards the preview source automatically.
        """
        if not _RV_AVAILABLE:
            return
        try:
            rv_path = _to_openrv_path(path)

            if self._preview_fs is None:
                # First preview in this series — save current view.
                self._pre_preview_view = _view_node()
                fs, group = _add_source(rv_path)
                if fs:
                    self._preview_fs = fs
                    self._preview_group = group
                    self._preview_path = path
                    if group:
                        _rvc.setViewNode(group)
            else:
                # Reuse existing preview slot: swap media in-place.
                try:
                    _rvc.setSourceMedia(self._preview_fs, [rv_path], "")
                    self._preview_path = path
                    if self._preview_group:
                        _rvc.setViewNode(self._preview_group)
                except Exception:
                    # setSourceMedia failed (e.g. node deleted externally);
                    # fall back to a fresh source.
                    self._preview_fs = None
                    self._preview_group = None
                    self._preview_path = None
                    self.preview_media(path)
        except Exception as e:
            print(f"OpenRVHostInterface.preview_media error: {e}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clear_preview(self, switch_view=True):
        """Remove the preview source and optionally restore the prior view."""
        if self._preview_fs is None:
            return
        group = self._preview_group
        self._preview_fs = None
        self._preview_group = None
        self._preview_path = None
        if switch_view and self._pre_preview_view:
            try:
                _rvc.setViewNode(self._pre_preview_view)
            except Exception:
                pass
        self._pre_preview_view = None
        _delete_source_group(group)
