from gallery.issues.snapshots import GuideSnapshot, get_guide_snapshot


GuideReceipt = GuideSnapshot


class UnknownGuide(LookupError):
    pass


def get_guide_receipt(connection, guide_id: int) -> GuideReceipt:
    guide = get_guide_snapshot(connection, guide_id)
    if guide is None:
        raise UnknownGuide(f'没有导览发行 {guide_id}。')
    return guide
