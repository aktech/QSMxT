#!/usr/bin/env python3
import os
import osfclient
import cloudstor
import pytest
import tempfile
import glob
import nibabel as nib
import shutil
import datetime
import numpy as np
import pandas as pd
import seaborn as sns
import run_2_qsm as qsm
from scripts.sys_cmd import sys_cmd
from matplotlib import pyplot as plt
from scripts.logger import LogLevel, make_logger

run_workflow = True

def create_logger(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    return make_logger(
        logpath=os.path.join(log_dir, f"log_{str(datetime.datetime.now()).replace(':', '-').replace(' ', '_').replace('.', '')}.txt"),
        printlevel=LogLevel.INFO,
        writelevel=LogLevel.INFO,
        warnlevel=LogLevel.WARNING,
        errorlevel=LogLevel.ERROR
    )

@pytest.fixture
def bids_dir():
    tmp_dir = tempfile.gettempdir()
    if not os.path.exists(os.path.join(tmp_dir, 'bids-osf')):
        if not os.path.exists(os.path.join(tmp_dir, 'bids-osf.tar')):
            print("Downloading test data...")
            file_pointer = next(osfclient.OSF().project("9jc42").storage().files)
            file_handle = open(os.path.join(tmp_dir, 'bids-osf.tar'), 'wb')
            file_pointer.write_to(file_handle)
        print("Extracting test data...")
        sys_cmd(f"tar xf {os.path.join(tmp_dir, 'bids-osf.tar')} -C {tmp_dir}")
        sys_cmd(f"rm {os.path.join(tmp_dir, 'bids-osf.tar')}")
    return os.path.join(tmp_dir, 'bids-osf')

@pytest.fixture
def bids_dir_secret():
    tmp_dir = tempfile.gettempdir()
    if not os.path.exists(os.path.join(tmp_dir, 'bids-secret')):
        if not os.path.exists(os.path.join(tmp_dir, 'bids-secret.tar')):
            print("Downloading test data...")
            cloudstor.cloudstor(url=os.environ['DOWNLOAD_URL'], password=os.environ['DATA_PASS']).download('', os.path.join(tmp_dir, 'bids-secret.tar'))
        print("Extracting test data...")
        sys_cmd(f"tar xf {os.path.join(tmp_dir, 'bids-secret.tar')} -C {tmp_dir}")
        sys_cmd(f"rm {os.path.join(tmp_dir, 'bids-secret.tar')}")
    return os.path.join(tmp_dir, 'bids-secret')

def display_nii(
    nii_path=None, data=None, dim=0, title=None, slc=None, dpi=96, size=None, out_png=None, final_fig=True, title_fontsize=12,
    colorbar=False, cbar_label=None, cbar_orientation='vertical', cbar_nbins=None, cbar_fontsize=None, cbar_label_fontsize=8,
    **imshow_args
):
    data = data if data is not None else nib.load(nii_path).get_fdata()
    slc = slc or int(data.shape[0]/2)
    if dim == 0: slc_data = data[slc,:,:]
    if dim == 1: slc_data = data[:,slc,:]
    if dim == 2: slc_data = data[:,:,slc]
    if size:
        plt.figure(figsize=(size[0]/dpi, size[1]/dpi), dpi=dpi)
    else:
        plt.figure(dpi=dpi)
    plt.axis('off')
    plt.imshow(np.rot90(slc_data), **imshow_args)
    if colorbar:
        cbar = plt.colorbar(orientation=cbar_orientation, fraction=0.037, pad=0.04)
        if cbar_fontsize:
            cbar.ax.tick_params(labelsize=cbar_fontsize)
        if cbar_nbins:
            cbar.ax.locator_params(nbins=cbar_nbins)
        if cbar_label:
            if cbar_orientation == 'horizontal':
                cbar.ax.set_xlabel(cbar_label, fontsize=cbar_label_fontsize)
            else:
                cbar.ax.set_ylabel(cbar_label, fontsize=cbar_label_fontsize, rotation=90)
    if title:
        plt.title(title, fontsize=title_fontsize)
    if final_fig:
        if out_png:
            plt.savefig(out_png, bbox_inches='tight')
        else:
            plt.show()

def print_metrics(name, bids_path, qsm_path):
    qsm_file = glob.glob(os.path.join(qsm_path, "qsm_final", "*qsm*nii*"))[0]
    seg_file = glob.glob(os.path.join(bids_path, "sub-1", "ses-1", "extra_data", "*segmentation*nii*"))[0]
    chi_file = glob.glob(os.path.join(bids_path, "sub-1", "ses-1", "extra_data", "*chi*crop*nii*"))[0]
    mask_file = glob.glob(os.path.join(bids_path, "sub-1", "ses-1", "extra_data", "*brainmask*nii*"))[0]

    qsm = nib.load(qsm_file).get_fdata()
    seg = nib.load(seg_file).get_fdata()
    chi = nib.load(chi_file).get_fdata()
    mask = nib.load(mask_file).get_fdata()
    seg *= mask
    chi *= mask

    labels = { 
        1 : "Caudate",
        2 : "Globus pallidus",
        3 : "Putamen",
        4 : "Red nucleus",
        5 : "Dentate nucleus",
        6 : "SN and STN",
        7 : "Thalamus",
        8 : "White matter",
        9 : "Gray matter",
        10 : "CSF",
        11 : "Blood",
        12 : "Fat",
        13 : "Bone",
        14 : "Air",
        15 : "Muscle",
        16 : "Calcification"
    }

    columns = ["Label", "RMSE"]

    # whole brain
    qsm_values = qsm[mask == 1].flatten()
    chi_values = chi[mask == 1].flatten()
    rmse_column = np.sqrt(np.square(qsm_values - chi_values)).reshape(-1,1)
    labels_column = np.full(rmse_column.shape, "Whole brain")
    new_vals = np.append(labels_column, rmse_column, axis=1)
    metrics_np = np.array(new_vals)

    # other areas
    for label_num in labels.keys():
        qsm_values = qsm[seg == label_num].flatten()
        chi_values = chi[seg == label_num].flatten()
        rmse_column = np.sqrt(np.square(qsm_values - chi_values)).reshape(-1,1)
        labels_column = np.full(rmse_column.shape, labels[label_num])
        new_vals = np.append(labels_column, rmse_column, axis=1)
        metrics_np = np.append(metrics_np, new_vals, axis=0)

    metrics = pd.DataFrame(data=metrics_np, columns=columns)
    metrics['RMSE'] = metrics['RMSE'].astype(float)
    plt.figure(figsize=(15, 8), dpi=200)
    ax = sns.boxplot(data=metrics, x="Label", y="RMSE", color="seagreen")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(os.path.join(qsm_path, "qsm_final", "metrics.png"))
    plt.close()

    display_nii(data=qsm, dim=0, cmap='gray', vmin=-0.1, vmax=+0.1, colorbar=True, cbar_label='ppm', cbar_orientation='horizontal', cbar_nbins=3, out_png=os.path.join(qsm_path, "qsm_final", os.path.join(qsm_path, "qsm_final", "slice.png")))


def workflow(args, init_workflow, run_workflow, run_args, show_metrics=False, delete_workflow=False):
    assert(not (run_workflow == True and init_workflow == False))
    create_logger(args.output_dir)
    if init_workflow:
        wf = qsm.init_workflow(args)
    if init_workflow and run_workflow:
        qsm.set_env_variables()
        if run_args:
            args_dict = vars(args)
            for key, value in run_args.items():
                args_dict[key] = value
            wf = qsm.init_workflow(args)
        args_file = open(os.path.join(args.output_dir, "args.txt"), 'w')
        args_file.write(str(args))
        args_file.close()
        wf.run(plugin='MultiProc', plugin_args={'n_procs': args.n_procs})            
        if delete_workflow:
            shutil.rmtree(os.path.join(args.output_dir, "workflow_qsm"), ignore_errors=True)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, run_workflow, { 'tgvqsm_iterations' : 1, 'num_echoes' : 2, 'single_pass' : True })
])
def test_args_defaults(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm")
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)
            
@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, False, None)
])
def test_args_tgvqsm_defaults(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--qsm_algorithm", "tgv_qsm"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, False, { 'num_echoes' : 2, 'n_procs' : 1 })
])
def test_args_nextqsm_defaults(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--qsm_algorithm", "nextqsm"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "nextqsm")
    assert(args.masking == "bet-firstecho")
    assert(args.two_pass == False)
    assert(args.single_pass == True)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(args.nextqsm_unwrapping_algorithm == "romeo")
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)
    
@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, False, { 'num_echoes' : 2, 'n_procs' : 1 })
])
def test_args_nextqsm_laplacian(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--qsm_algorithm", "nextqsm",
        "--nextqsm_unwrapping_algorithm", "laplacian"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "nextqsm")
    assert(args.masking == "bet-firstecho")
    assert(args.two_pass == False)
    assert(args.single_pass == True)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(args.nextqsm_unwrapping_algorithm == "laplacian")
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, False, None)
])
def test_args_singlepass(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--single_pass"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == False)
    assert(args.single_pass == True)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, run_workflow, { 'tgvqsm_iterations' : 1, 'num_echoes' : 2, 'single_pass' : True })
])
def test_args_inhomogeneity_correction_bet(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--inhomogeneity_correction",
        "--masking", "bet"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "bet")
    assert(args.two_pass == False)
    assert(args.single_pass == True)
    assert(args.inhomogeneity_correction == True)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, run_workflow, { 'tgvqsm_iterations' : 1, 'num_echoes' : 2, 'single_pass' : True })
])
def test_args_inhomogeneity_correction_magnitudebased(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--inhomogeneity_correction",
        "--masking", "magnitude-based"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "magnitude-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == True)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, False, None)
])
def test_args_inhomogeneity_correction_invalid(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--inhomogeneity_correction",
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, run_workflow, { 'tgvqsm_iterations' : 1, 'num_echoes' : 2, 'single_pass' : True })
])
def test_args_addbet(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--add_bet"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == True)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, False, None)
])
def test_args_addbet_invalid(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--add_bet",
        "--masking", "bet"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "bet")
    assert(args.two_pass == False)
    assert(args.single_pass == True)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, run_workflow, { 'tgvqsm_iterations' : 1, 'num_echoes' : 2, 'single_pass' : True })
])
def test_args_use_existing_masks(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--use_existing_masks"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == True)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, False, None)
])
def test_args_numechoes(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "qsm"),
        "--num_echoes", "3"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(args.num_echoes == 3)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)


@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, True, { 'tgvqsm_iterations' : 1, 'num_echoes' : 2, 'single_pass' : True })
])
def test_bids_secret(bids_dir_secret, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir_secret,
        os.path.join(tempfile.gettempdir(), "qsm-secret")
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir_secret))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "qsm-secret"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "phase-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args)

    # upload filename
    if os.environ.get('BRANCH'):
        results_tar = f"{str(datetime.datetime.now()).replace(':', '-').replace(' ', '_').replace('.', '')}_{os.environ['BRANCH']}.tar"
    else:
        results_tar = f"{str(datetime.datetime.now()).replace(':', '-').replace(' ', '_').replace('.', '')}.tar"
    
    # zip up results
    shutil.rmtree(os.path.join(args.output_dir, "workflow_qsm"))
    sys_cmd(f"tar -cf {results_tar} {args.output_dir}")

    # upload results
    cs = cloudstor.cloudstor(url=os.environ['UPLOAD_URL'], password=os.environ['DATA_PASS'])
    cs.upload(results_tar, results_tar)


@pytest.mark.parametrize("init_workflow, run_workflow, run_args", [
    (True, run_workflow, None)
])
def test_metrics(bids_dir, init_workflow, run_workflow, run_args):
    args = qsm.process_args(qsm.parse_args([
        bids_dir,
        os.path.join(tempfile.gettempdir(), "public-outputs", "test_metrics"),
        "--masking", "magnitude-based"
    ]))
    
    assert(args.bids_dir == os.path.abspath(bids_dir))
    assert(args.output_dir == os.path.join(tempfile.gettempdir(), "public-outputs", "test_metrics"))
    assert(args.qsm_algorithm == "tgv_qsm")
    assert(args.masking == "magnitude-based")
    assert(args.two_pass == True)
    assert(args.single_pass == False)
    assert(args.inhomogeneity_correction == False)
    assert(args.add_bet == False)
    assert(args.use_existing_masks == False)
    assert(0 < args.n_procs <= int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    assert(0 < args.tgvqsm_threads < int(os.environ["NCPUS"]) if "NCPUS" in os.environ else int(os.cpu_count()))
    
    workflow(args, init_workflow, run_workflow, run_args, show_metrics=True)
    if run_workflow:
        print_metrics(str(args), args.bids_dir, args.output_dir)

# TODO
#  - check file outputs
#  - test axial resampling / obliquity
#  - test for errors that may occur within a run, including:
#    - no phase files present
#    - number of json files different from number of phase files
#    - no magnitude files present - default to phase-based masking
#    - use_existing_masks specified but none found - default to masking method
#    - use_existing_masks specified but number of masks > 1 and mismatches # of echoes 
#    - use_existing_masks specified and masks found:
#      - inhomogeneity_correction, two_pass, and add_bet should all disable

