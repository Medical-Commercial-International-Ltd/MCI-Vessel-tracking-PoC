"""Run with .venv-satellite/Scripts/python.exe; no network or real satellite downloads."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np
from PIL import Image

spec = importlib.util.spec_from_file_location('renderer', Path(__file__).resolve().parents[1]/'scripts/render_satellite.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class RendererChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.source = Path(self.directory.name)/'sample.nc'
        self.output = Path(self.directory.name)/'sample.png'
        with h5py.File(self.source,'w') as data:
            projection=data.create_dataset('goes_imager_projection',data=0)
            for name,value in {'perspective_point_height':35786023, 'longitude_of_projection_origin':-75.2,
                               'semi_major_axis':6378137,'semi_minor_axis':6356752.31414}.items():
                projection.attrs[name]=np.array([value])
            data.create_dataset('x',data=np.linspace(-0.02,0.02,81))
            data.create_dataset('y',data=np.linspace(0.02,-0.02,81))
            cmi=data.create_dataset('CMI',data=np.broadcast_to(np.arange(81,dtype=np.uint16)*50,(81,81)))
            cmi.attrs['scale_factor']=np.array([0.01]); cmi.attrs['add_offset']=np.array([190.0]); cmi.attrs['_FillValue']=65535
            data.create_dataset('DQF',data=np.zeros((81,81),dtype=np.uint8))
            data.attrs['time_coverage_start']=np.bytes_('2025-09-30T12:00:20.4Z')
            data.attrs['time_coverage_end']=np.bytes_('2025-09-30T12:09:52.4Z')
    def tearDown(self): self.directory.cleanup()
    def request(self,bounds=None):
        return {'input':str(self.source),'output':str(self.output),'bounds':bounds or [-76.2,-1,-74.2,1],'width':32,'height':32}
    def test_geolocation_scale_metadata_and_png(self):
        metadata=renderer.render(self.request())
        with Image.open(self.output) as image:
            self.assertEqual(image.size,(32,32))
            pixels=np.array(image)
        self.assertGreater(pixels[16,0,0],pixels[16,-1,0])
        self.assertTrue(np.all(pixels[:,:,3]==255))
        self.assertEqual(metadata['acquiredAt'],'2025-09-30T12:00:20.4Z')
        self.assertEqual(metadata['acquisitionEnd'],'2025-09-30T12:09:52.4Z')
    def test_unusable_quality_does_not_create_false_image(self):
        with h5py.File(self.source,'r+') as data: data['DQF'][:]=2
        with self.assertRaisesRegex(ValueError,'No usable'): renderer.render(self.request())
    def test_far_side_of_earth_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'): renderer.render(self.request([100,0,110,10]))


if __name__=='__main__': unittest.main()
