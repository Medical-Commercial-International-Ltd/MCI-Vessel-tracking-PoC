"""Presentation-only portraits for the fixed fictional demonstration identities."""

CREW_PORTRAITS = {
    f'fictional-{case}-{index}': f'/static/crew/{slug}.png'
    for case in ('aurora', 'tempest')
    for index, slug in enumerate(('cameron-vale', 'emery-cole', 'elliot-hart'))
}
