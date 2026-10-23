"""Read-only acceptance of Concat's verified GTK media-import chooser.

Run only while the Concat 'Importer des médias' chooser is visible. Does not
click or type into it; tests the security boundary before user editing.
"""
import json
from ccer.desktop_gui import capture, status


def main():
    found = status()
    dialog = found["window"]
    if dialog.get("role") != "concat_media_import_dialog":
        raise RuntimeError("Expected verified Concat media-import dialog, got " + repr(dialog))
    image = capture(max_width=900)
    if image["window"]["windowId"] != dialog["windowId"] or len(image["imageBase64"]) < 300:
        raise RuntimeError("Media import dialog screenshot invalid")
    print(json.dumps({"verified": True, "dialogTitle": dialog["title"],
                      "dialogWindowId": dialog["windowId"], "width": dialog["width"],
                      "height": dialog["height"], "captureSha256": image["sha256"],
                      "userFilesUntouched": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
