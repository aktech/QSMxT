import os
import nibabel as nib
import numpy as np
import nilearn.image
import warnings
from nipype.interfaces.base import SimpleInterface, BaseInterfaceInputSpec, TraitedSpec, File, traits

def resample_to_axial(mag_nii, pha_nii, mask_nii=None):
    # calculate base affine
    voxel_size = np.array(mag_nii.header.get_zooms())
    resolution = np.array(mag_nii.header.get_data_shape())
    origin = np.array(voxel_size * resolution / 2)
    base_affine = np.eye(4)
    np.fill_diagonal(base_affine, voxel_size * np.sign(np.diag(mag_nii.affine))[:3])
    base_affine[3,3] = 1
    base_affine[:3,3] = origin * -np.sign(np.diag(mag_nii.affine)[:3])

    # compute real and imaginary components from magnitude and phase
    pha = pha_nii.get_fdata()
    mag = mag_nii.get_fdata()
    real = mag * np.cos(pha)
    imag = mag * np.sin(pha)
    cplx_header = mag_nii.header.copy()
    cplx_header.set_data_dtype(np.float32)
    real_nii = nib.Nifti1Image(real, affine=pha_nii.affine, header=cplx_header)
    imag_nii = nib.Nifti1Image(imag, affine=pha_nii.affine, header=cplx_header)

    # resample real and imaginary to base affine
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        real_rot_nii = nilearn.image.resample_img(real_nii, target_affine=base_affine, target_shape=None, interpolation='continuous')
        imag_rot_nii = nilearn.image.resample_img(imag_nii, target_affine=base_affine, target_shape=None, interpolation='continuous')
        mask_rot_nii = nilearn.image.resample_img(mask_nii, target_affine=base_affine, target_shape=None, interpolation='nearest') if mask_nii else None

    # convert real and imaginary to magnitude and phase
    real_rot = real_rot_nii.get_fdata()
    imag_rot = imag_rot_nii.get_fdata()
    mag_rot = np.array(np.round(np.hypot(real_rot, imag_rot), 0), dtype=mag_nii.header.get_data_dtype())
    pha_rot = np.array(np.arctan2(imag_rot, real_rot), dtype=np.float16)

    # create nifti objects
    mag_rot_nii = nib.Nifti1Image(mag_rot, affine=real_rot_nii.affine, header=mag_nii.header)
    pha_rot_nii = nib.Nifti1Image(pha_rot, affine=real_rot_nii.affine, header=pha_nii.header)

    return mag_rot_nii, pha_rot_nii, mask_rot_nii

def resample_files(mag_file, pha_file, mask_file=None, obliquity_threshold=None):
    # load data
    print(f"Loading mag={os.path.split(mag_file)[1]}...")
    mag_nii = nib.load(mag_file)
    print(f"Loading pha={os.path.split(pha_file)[1]}...")
    pha_nii = nib.load(pha_file)
    if mask_file:
        print(f"Loading mask={os.path.split(mask_file)[1]}...")
    mask_nii = nib.load(mask_file) if mask_file else None        

    # check obliquity
    obliquity = np.rad2deg(nib.affines.obliquity(mag_nii.affine))
    obliquity_norm = np.linalg.norm(obliquity)
    if obliquity_threshold and obliquity_norm < obliquity_threshold:
        print(f"Obliquity = {obliquity}; norm = {obliquity_norm} < {obliquity_threshold}; no resampling needed.")
        return mag_file, pha_file, mask_file
    print(f"Obliquity = {obliquity}; norm = {obliquity_norm} >= {obliquity_threshold}; resampling will commence.")

    # resample
    mag_rot_nii, pha_rot_nii, mask_rot_nii = resample_to_axial(mag_nii, pha_nii, mask_nii)
    
    # save results
    mag_fname = os.path.split(mag_file)[1].split('.')[0]
    pha_fname = os.path.split(pha_file)[1].split('.')[0]
    mag_extension = ".".join(mag_file.split('.')[1:])
    pha_extension = ".".join(pha_file.split('.')[1:])
    mag_resampled_fname = os.path.abspath(f"{mag_fname}_resampled.{mag_extension}")
    pha_resampled_fname = os.path.abspath(f"{pha_fname}_resampled.{pha_extension}")
    print(f"Saving mag={mag_resampled_fname}")
    nib.save(mag_rot_nii, mag_resampled_fname)
    print(f"Saving pha={pha_resampled_fname}")
    nib.save(pha_rot_nii, pha_resampled_fname)
    
    mask_resampled_fname = "placeholder"
    if mask_rot_nii:
        mask_fname = os.path.split(mask_file)[1].split('.')[0]
        mask_extension = '.'.join(mask_file.split('.')[1:])
        mask_resampled_fname = os.path.abspath(f"{mask_fname}_resampled.{mask_extension}")
        print(f"Saving mask={mask_resampled_fname}")
        nib.save(mask_rot_nii, mask_resampled_fname)

    return mag_resampled_fname, pha_resampled_fname, mask_resampled_fname


def resample_like(in_file, in_like, interpolation='continuous'):
    in_nii = nib.load(in_file)
    in_like_nii = nib.load(in_like)
    if np.array_equal(in_nii.affine, in_like_nii.affine):
        return in_file
    in_nii_resampled = nilearn.image.resample_img(in_nii, target_affine=in_like_nii.affine, target_shape=np.array(in_like_nii.header.get_data_shape()), interpolation=interpolation)
    in_fname = os.path.split(in_file)[1].split('.')[0]
    in_extension = ".".join(in_file.split('.')[1:])
    in_resampled_fname = os.path.abspath(f"{in_fname}_resampled.{in_extension}")
    nib.save(in_nii_resampled, in_resampled_fname)
    return in_resampled_fname


class AxialSamplingInputSpec(BaseInterfaceInputSpec):
    in_mag = File(mandatory=True, exists=True)
    in_pha = File(mandatory=True, exists=True)
    in_mask = File(mandatory=False, exists=True)
    obliquity_threshold = traits.Float(mandatory=False)


class AxialSamplingOutputSpec(TraitedSpec):
    out_mag = File(exists=True)
    out_pha = File(exists=True)
    out_mask = File(mandatory=False)


class AxialSamplingInterface(SimpleInterface):
    input_spec = AxialSamplingInputSpec
    output_spec = AxialSamplingOutputSpec

    def _run_interface(self, runtime):
        out_mag, out_pha, out_mask = resample_files(
            mag_file=self.inputs.in_mag,
            pha_file=self.inputs.in_pha,
            mask_file=self.inputs.in_mask,
            obliquity_threshold=self.inputs.obliquity_threshold
        )
        self._results['out_mag'] = out_mag
        self._results['out_pha'] = out_pha
        self._results['out_mask'] = out_mask
        
        return runtime


class ResampleLikeInputSpec(BaseInterfaceInputSpec):
    in_file = File(mandatory=True, exists=True)
    in_like = File(mandatory=True, exists=True)


class ResampleLikeOutputSpec(TraitedSpec):
    out_file = File(exists=True)


class ResampleLikeInterface(SimpleInterface):
    input_spec = ResampleLikeInputSpec
    output_spec = ResampleLikeOutputSpec

    def _run_interface(self, runtime):
        out_file = resample_like(self.inputs.in_file, self.inputs.in_like)
        self._results['out_file'] = out_file
        return runtime

