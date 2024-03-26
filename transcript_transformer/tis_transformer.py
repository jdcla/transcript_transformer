import os
import sys
import numpy as np
import yaml
import h5py
from importlib import resources as impresources
from argparse import Namespace

from .transcript_transformer import train, predict
from .argparser import Parser, parse_config_file
from .util_functions import define_folds
from .pretrained import tis_transformer_models
from .data import process_seq_data
from .processing import construct_output_table


def parse_args():
    parser = Parser(description="Run Ribo-former", stage="train")
    parser.add_data_args()
    parser.add_argument(
        "--factor",
        type=float,
        default=1,
        help="Determines the number of model predictions in the result table."
        "This factor is multiplied to the number of canonical "
        "TISs present on evaluated transcripts.",
    )
    parser.add_argument(
        "--prob_cutoff",
        type=float,
        default=0.03,
        help="Determines the minimum model output score required for model "
        "predictions to be included in the result table.",
    )
    parser.add_argument(
        "--data",
        action="store_true",
        help="only perform pre-processing of data",
    )
    parser.add_argument(
        "--results",
        action="store_true",
        help="only perform processing of model predictions",
    )
    parser.add_comp_args()
    parser.add_training_args()
    parser.add_train_loading_args(pretrain=False)
    parser.add_evaluation_args()
    parser.add_architecture_args()
    args = load_args(
        (impresources.files(tis_transformer_models) / "default_config.yml")
    )
    args.__dict__.update(**vars(parser.parse_args(sys.argv[1:])))
    args = parse_config_file(args)
    if args.out_prefix is None:
        args.out_prefix = os.path.splitext(args.input_config)[0]
    assert ~args.results and ~args.data, (
        "cannot only do processing of data and results, disable either"
        " --data_process or --result_process"
    )
    args.mlm, args.mask_frac, args.rand_frac = False, False, False
    # remove riboformer specific properties
    args.use_seq = True
    args.use_ribo = False
    args.cond["grouped"] = [{}]
    return args


def load_args(path):
    with open(path, "r") as fh:
        input_config = yaml.safe_load(fh)

    return Namespace(**input_config)


def main():
    args = parse_args()
    prefix = f"{args.out_prefix}_seq"
    if not args.results:
        process_seq_data(
            args.h5_path, args.gtf_path, args.fa_path, args.backup_path, ~args.no_backup
        )
    if not (args.data or args.results):
        args.use_seq = True
        args.use_ribo = False
        args.input_type = "config"
        f = h5py.File(args.h5_path, "r")["transcript"]
        contigs = np.array(f["contig"])
        tr_lens = np.array(f["tr_len"])
        f.close()
        contig_set = np.unique(contigs)
        contig_lens = {}
        for contig in contig_set:
            mask = contigs == contig
            contig_lens[contig] = sum(tr_lens[mask])
        folds = define_folds(contig_lens, 0.2, 0.2)
        for i, fold in folds.items():
            args.__dict__.update(fold)
            trainer, model = train(args, test_model=False, enable_model_summary=False)
            args.out_prefix = f"{prefix}_f{i}"
            predict(args, trainer=trainer, model=model, postprocess=False)
        merge_outputs(prefix, folds.keys())

        f = h5py.File(args.h5_path, "a")
        grp = f["transcript"]
        out = np.load(f"{prefix}.npy", allow_pickle=True)
        construct_output_table(
            grp, out, prefix, args.factor, args.prob_cutoff, ribo=args.use_ribo
        )
        f_tr_ids = np.array(grp["id"])
        xsorted = np.argsort(f_tr_ids)
        tr_ids = np.hstack([o[0] for o in out])

        pred_to_h5_args = xsorted[np.searchsorted(f_tr_ids[xsorted], tr_ids)]
        pred_arr = np.empty(shape=(len(f_tr_ids),), dtype=object)
        pred_arr.fill(np.array([], dtype=np.float32))
        for idx, (_, pred, _) in zip(pred_to_h5_args, out):
            pred_arr[idx] = pred
        dtype = h5py.vlen_dtype(np.dtype("float32"))
        if "seq_output" in grp.keys():
            print("--> Overwriting results in local h5 database...")
            del grp["seq_output"]
        else:
            print("--> Writing results to local h5 database...")
        grp.create_dataset("seq_output", data=pred_arr, dtype=dtype)
        f.close()
        if not args.no_backup:
            if not args.backup_path:
                args.backup_path = os.path.splitext(args.gtf_path)[0] + ".h5"
            if os.path.isfile(args.backup_path):
                f = h5py.File(args.backup_path, "a")
                grp = f["transcript"]
                if "seq_output" in grp.keys():
                    print("--> Overwriting results in backup h5 database...")
                    del grp["seq_output"]
                else:
                    print("--> Writing results to backup h5 database...")
                grp.create_dataset("seq_output", data=pred_arr, dtype=dtype)
                f.close()
    if not args.data:
        f = h5py.File(args.h5_path, "r")
        construct_output_table(
            f["transcript"], f"{args.out_prefix}_seq", args.factor, args.prob_cutoff
        )
        f.close()


def merge_outputs(prefix, keys):
    out = np.vstack([np.load(f"{prefix}_f{i}.npy", allow_pickle=True) for i in keys])
    np.save(f"{prefix}.npy", out)
    [os.remove(f"{prefix}_f{i}.npy") for i in keys]


if __name__ == "__main__":
    main()
