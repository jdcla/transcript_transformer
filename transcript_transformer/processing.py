import numpy as np
import h5max
from tqdm import tqdm
import pandas as pd
import polars as pl

from .util_functions import (
    construct_prot,
    time,
    vec2DNA,
    find_distant_exon_coord,
    transcript_region_to_exons,
)

headers = [
    "id",
    "contig",
    "biotype",
    "strand",
    "canonical_TIS_coord",
    "canonical_TIS_exon_idx",
    "canonical_TIS_idx",
    "canonical_TTS_coord",
    "canonical_TTS_idx",
    "canonical_prot_id",
    "exon_coords",
    "exon_idxs",
    "gene_id",
    "gene_name",
    "support_lvl",
    "tag",
    "tr_len",
]


out_headers = [
    "seqname",
    "ORF_id",
    "tr_id",
    "TIS_pos",
    "output",
    "output_rank",
    "seq_output",
    "start_codon",
    "stop_codon",
    "ORF_len",
    "TTS_pos",
    "TTS_on_transcript",
    "reads_in_tr",
    "reads_in_ORF",
    "reads_out_ORF",
    "in_frame_read_perc",
    "ORF_type",
    "ORF_equals_CDS",
    "tr_biotype",
    "tr_support_lvl",
    "tr_tag",
    "tr_len",
    "dist_from_canonical_TIS",
    "frame_wrt_canonical_TIS",
    "correction",
    "TIS_coord",
    "TIS_exon",
    "TTS_coord",
    "TTS_exon",
    "strand",
    "gene_id",
    "gene_name",
    "canonical_TIS_coord",
    "canonical_TIS_exon_idx",
    "canonical_TIS_idx",
    "canonical_TTS_coord",
    "canonical_TTS_idx",
    "canonical_prot_id",
    "prot",
]

decode = [
    "seqname",
    "tr_id",
    "tr_biotype",
    "tr_support_lvl",
    "tr_tag",
    "strand",
    "gene_id",
    "gene_name",
    "canonical_prot_id",
]


def construct_output_table(
    f,
    out_prefix,
    prob_cutoff=0.15,
    correction=False,
    dist=9,
    start_codons=".*TG$",
    min_ORF_len=15,
    remove_duplicates=True,
    exclude_invalid_TTS=True,
    ribo=None,
):
    f_tr_ids = np.array(f["id"])
    has_seq_output = "seq_output" in f.keys()
    has_ribo_output = ribo is not None
    assert has_seq_output or has_ribo_output, "no model predictions found"
    print(f"--> Processing {out_prefix}...")

    if has_ribo_output:
        tr_ids = np.array([o[0].split(b"|")[1] for o in ribo])
        ribo_id = ribo[0][0].split(b"|")[0]
        xsorted = np.argsort(f_tr_ids)
        pred_to_h5_args = xsorted[np.searchsorted(f_tr_ids[xsorted], tr_ids)]
        preds = np.hstack([o[1] for o in ribo])

    else:
        mask = [len(o) > 0 for o in np.array(f["seq_output"])]
        preds = np.hstack(np.array(f["seq_output"]))
        pred_to_h5_args = np.where(mask)[0]
    # map pred ids to database id
    k = (preds > prob_cutoff).sum()
    if k == 0:
        print(
            f"!-> No predictions with an output probability higher than {prob_cutoff}"
        )
        return None
    lens = np.array(f["tr_len"])[pred_to_h5_args]
    cum_lens = np.cumsum(np.insert(lens, 0, 0))
    idxs = np.argpartition(preds, -k)[-k:]

    orf_dict = {"f_idx": [], "TIS_idx": []}
    for idx in idxs:
        idx_tr = np.where(cum_lens > idx)[0][0] - 1
        orf_dict["TIS_idx"].append(idx - cum_lens[idx_tr])
        orf_dict["f_idx"].append(pred_to_h5_args[idx_tr])
    if has_seq_output:
        seq_out = [
            f["seq_output"][i][j]
            for i, j in zip(orf_dict["f_idx"], orf_dict["TIS_idx"])
        ]
        orf_dict.update({"seq_output": seq_out})
    orf_dict.update(
        {f"{header}": np.array(f[f"{header}"])[orf_dict["f_idx"]] for header in headers}
    )
    orf_dict.update(orf_dict)
    df_out = pd.DataFrame(data=orf_dict)
    df_out = df_out.rename(
        columns={
            "id": "tr_id",
            "support_lvl": "tr_support_lvl",
            "biotype": "tr_biotype",
            "tag": "tr_tag",
        }
    )
    df_out["correction"] = np.nan

    df_dict = {
        "start_codon": [],
        "stop_codon": [],
        "prot": [],
        "TTS_exon": [],
        "TTS_on_transcript": [],
        "TIS_coord": [],
        "TIS_exon": [],
        "TTS_coord": [],
        "TTS_coord": [],
        "TTS_pos": [],
        "ORF_len": [],
    }

    TIS_idxs = df_out.TIS_idx.copy()
    corrections = df_out.correction.copy()
    for i, row in tqdm(
        df_out.iterrows(), total=len(df_out), desc=f"{time()}: parsing ORF information "
    ):
        tr_seq = f["seq"][row.f_idx]
        TIS_idx = row.TIS_idx
        if correction and not np.array_equal(tr_seq[TIS_idx : TIS_idx + 3], [0, 1, 3]):
            low_bound = max(0, TIS_idx - (dist * 3))
            tr_seq_win = tr_seq[low_bound : TIS_idx + (dist + 1) * 3]
            atg = [0, 1, 3]
            matches = [
                x
                for x in range(len(tr_seq_win))
                if np.array_equal(tr_seq_win[x : x + len(atg)], atg)
            ]
            matches = np.array(matches) - min(TIS_idx, dist * 3)
            matches = matches[matches % 3 == 0]
            if len(matches) > 0:
                match = matches[np.argmin(abs(matches))]
                corrections[row.name] = match
                TIS_idx = TIS_idx + match
                TIS_idxs[row.name] = TIS_idx
        DNA_frag = vec2DNA(tr_seq[TIS_idx:])
        df_dict["start_codon"].append(DNA_frag[:3])
        prot, has_stop, stop_codon = construct_prot(DNA_frag)
        df_dict["stop_codon"].append(stop_codon)
        df_dict["prot"].append(prot)
        df_dict["TTS_on_transcript"].append(has_stop)
        df_dict["ORF_len"].append(len(prot) * 3)
        TIS_exon = np.sum(TIS_idx >= row.exon_idxs) // 2 + 1
        TIS_exon_idx = TIS_idx - row.exon_idxs[(TIS_exon - 1) * 2]
        if row.strand == b"+":
            TIS_coord = row.exon_coords[(TIS_exon - 1) * 2] + TIS_exon_idx
        else:
            TIS_coord = row.exon_coords[(TIS_exon - 1) * 2 + 1] - TIS_exon_idx
        if has_stop:
            TTS_idx = TIS_idx + df_dict["ORF_len"][-1]
            TTS_pos = TTS_idx + 1
            TTS_exon = np.sum(TTS_idx >= row.exon_idxs) // 2 + 1
            TTS_exon_idx = TTS_idx - row.exon_idxs[(TTS_exon - 1) * 2]
            if row.strand == b"+":
                TTS_coord = row.exon_coords[(TTS_exon - 1) * 2] + TTS_exon_idx
            else:
                TTS_coord = row.exon_coords[(TTS_exon - 1) * 2 + 1] - TTS_exon_idx
        else:
            TTS_coord, TTS_exon, TTS_pos = -1, -1, -1

        df_dict["TIS_coord"].append(TIS_coord)
        df_dict["TIS_exon"].append(TIS_exon)
        df_dict["TTS_pos"].append(TTS_pos)
        df_dict["TTS_exon"].append(TTS_exon)
        df_dict["TTS_coord"].append(TTS_coord)

    df_out = df_out.assign(**df_dict)
    df_out["TIS_idx"] = TIS_idxs
    df_out["correction"] = corrections
    df_out["seqname"] = df_out["contig"]
    df_out["TIS_pos"] = df_out["TIS_idx"] + 1
    df_out["output"] = preds[idxs]
    df_out = df_out.sort_values("output", ascending=False)
    df_out["output_rank"] = np.arange(len(df_out))

    df_out["dist_from_canonical_TIS"] = df_out["TIS_idx"] - df_out["canonical_TIS_idx"]
    df_out.loc[df_out["canonical_TIS_idx"] == -1, "dist_from_canonical_TIS"] = np.nan
    df_out["frame_wrt_canonical_TIS"] = df_out["dist_from_canonical_TIS"] % 3

    if has_seq_output:
        seq_out = [
            f["seq_output"][i][j]
            for i, j in zip(orf_dict["f_idx"], orf_dict["TIS_idx"])
        ]
        orf_dict.update({"seq_output": seq_out})

    if has_ribo_output:
        ribo_subsets = np.array(ribo_id.split(b"&"))
        sparse_reads_set = []
        for subset in ribo_subsets:
            sparse_reads = h5max.load_sparse(
                f[f"riboseq/{subset.decode()}/5/"], df_out["f_idx"], to_numpy=False
            )
            sparse_reads_set.append(sparse_reads)
        sparse_reads = np.add.reduce(sparse_reads_set)
        df_out["reads_in_tr"] = np.array([s.sum() for s in sparse_reads])
        reads_in = []
        reads_out = []
        in_frame_read_perc = []
        for i, (_, row) in tqdm(
            enumerate(df_out.iterrows()),
            total=len(df_out),
            desc=f"{time()}: parsing ribo-seq information ",
        ):
            end_of_ORF_idx = row.TIS_pos + row.ORF_len - 1
            reads_in_ORF = sparse_reads[i][:, row.TIS_pos - 1 : end_of_ORF_idx].sum()
            reads_out_ORF = sparse_reads[i].sum() - reads_in_ORF
            in_frame_reads = sparse_reads[i][
                :, np.arange(row["TIS_pos"] - 1, end_of_ORF_idx, 3)
            ].sum()
            reads_in.append(reads_in_ORF)
            reads_out.append(reads_out_ORF)

            in_frame_read_perc.append(in_frame_reads / max(reads_in_ORF, 1))

        df_out["reads_in_ORF"] = reads_in
        df_out["reads_out_ORF"] = reads_out
        df_out["in_frame_read_perc"] = in_frame_read_perc

    TIS_coords = np.array(f["canonical_TIS_coord"])
    TTS_coords = np.array(f["canonical_TTS_coord"])
    cds_lens = np.array(f["canonical_TTS_idx"]) - np.array(f["canonical_TIS_idx"])
    orf_type = []
    is_cds = []
    for i, row in tqdm(
        df_out.iterrows(),
        total=len(df_out),
        desc=f"{time()}: parsing ORF type information ",
    ):
        TIS_mask = row["TIS_coord"] == TIS_coords
        TTS_mask = row["TTS_coord"] == TTS_coords
        len_mask = row.ORF_len == cds_lens
        is_cds.append(np.logical_and.reduce([TIS_mask, TTS_mask, len_mask]).any())

        if row["canonical_TIS_idx"] != -1:
            if row["canonical_TIS_idx"] == row["TIS_pos"] - 1:
                orf_type.append("annotated CDS")
            elif row["TIS_pos"] > row["canonical_TTS_idx"] + 1:
                orf_type.append("dORF")
            elif row["TTS_pos"] < row["canonical_TIS_idx"] + 1:
                orf_type.append("uORF")
            elif row["TIS_pos"] < row["canonical_TIS_idx"] + 1:
                if row["TTS_pos"] == row["canonical_TTS_idx"] + 1:
                    orf_type.append("N-terminal extension")
                else:
                    orf_type.append("uoORF")
            elif row["TTS_pos"] > row["canonical_TTS_idx"] + 1:
                orf_type.append("doORF")
            else:
                if row["TTS_pos"] == row["canonical_TTS_idx"] + 1:
                    orf_type.append("N-terminal truncation")
                else:
                    orf_type.append("intORF")
        else:
            shares_TIS_coord = row["TIS_coord"] in TIS_coords
            shares_TTS_coord = row["TTS_coord"] in TTS_coords
            if shares_TIS_coord or shares_TTS_coord:
                orf_type.append("CDS variant")
            else:
                orf_type.append("other")
    df_out["ORF_type"] = orf_type
    df_out["ORF_equals_CDS"] = is_cds
    df_out.loc[df_out["tr_biotype"] == b"lncRNA", "ORF_type"] = "lncRNA-ORF"
    # decode strs
    for header in decode:
        df_out[header] = df_out[header].str.decode("utf-8")
    df_out["ORF_id"] = df_out["tr_id"] + "_" + df_out["TIS_pos"].astype(str)
    # re-arrange columns
    o_headers = [h for h in out_headers if h in df_out.columns]
    df_out = df_out.loc[:, o_headers].sort_values("output_rank")
    # remove duplicates
    if correction and remove_duplicates:
        df_out = df_out.drop_duplicates("ORF_id")
    if exclude_invalid_TTS:
        df_out = df_out[df_out["TTS_on_transcript"]]
    df_out = df_out[df_out["ORF_len"] > min_ORF_len]
    df_out = df_out[df_out["start_codon"].str.contains(start_codons)]
    df_out.to_csv(f"{out_prefix}.csv", index=None)

    return df_out


def process_seq_preds(ids, preds, seqs, min_prob):
    df = pd.DataFrame(
        columns=[
            "ID",
            "tr_len",
            "TIS_pos",
            "output",
            "start_codon",
            "TTS_pos",
            "stop_codon",
            "TTS_on_transcript",
            "prot_len",
            "prot_seq",
        ]
    )
    num = 0
    mask = [np.where(pred > min_prob)[0] for pred in preds]
    for i, idxs in enumerate(mask):
        tr = seqs[i]
        for idx in idxs:
            prot_seq, has_stop, stop_codon = construct_prot(tr[idx:])
            TTS_pos = idx + len(prot_seq) * 3
            df.loc[num] = [
                ids[i][0],
                len(tr),
                idx + 1,
                preds[i][idx],
                tr[idx : idx + 3],
                TTS_pos,
                stop_codon,
                has_stop,
                len(prot_seq),
                prot_seq,
            ]
            num += 1
    return df


def csv_to_gtf(f, df, out_prefix, exclude_annotated=True):
    """convert RiboTIE result table to GTF
    Args:
        csv_path (str): path to result table
        gtf_path (str, optional): Path to gtf file. function appends lines if file already exists.
        exclude_cdss (bool, optional): Exclude annotated coding sequences. Defaults to True.
        output_th (float, optional): Model output threshold to determine positive set. Defaults to 0.15.
        filt_TTS_on_tr (bool, optional): Exclude predictions with no valid TTS. Defaults to True.
    """

    df = pl.from_pandas(df)
    if exclude_annotated:
        df = df.filter(pl.col("ORF_type") != "annotated CDS")
    df = df.fill_null("NA")
    f_ids = np.array(f["transcript/id"])
    xsorted = np.argsort(f_ids)
    pred_to_h5_args = xsorted[np.searchsorted(f_ids[xsorted], df["tr_id"])]
    exon_coords = np.array(f["transcript/exon_coords"])[pred_to_h5_args]
    gtf_parts = []
    for tis, stop_codon_start, strand, exons in zip(
        df["TIS_coord"], df["TTS_coord"], df["strand"], exon_coords
    ):
        start_codon_stop = find_distant_exon_coord(tis, 2, strand, exons)
        start_parts, start_exons = transcript_region_to_exons(
            tis, start_codon_stop, strand, exons
        )
        # acquire cds stop coord from stop codon coord.
        if stop_codon_start != -1:
            stop_codon_stop = find_distant_exon_coord(
                stop_codon_start, 2, strand, exons
            )
            stop_parts, stop_exons = transcript_region_to_exons(
                stop_codon_start, stop_codon_stop, strand, exons
            )
            if strand == "+":
                tts = stop_codon_start - 1
            else:
                tts = stop_codon_start + 1
        else:
            stop_parts, stop_exons = np.empty(start_parts.shape), np.empty(
                start_exons.shape
            )
            tts = -1

        cds_parts, cds_exons = transcript_region_to_exons(tis, tts, strand, exons)
        coords_packed = np.vstack(
            [
                start_parts.reshape(-1, 2),
                cds_parts.reshape(-1, 2),
                stop_parts.reshape(-1, 2),
            ]
        )
        exons_packed = np.hstack([start_exons, cds_exons, stop_exons]).reshape(-1, 1)
        features_packed = np.hstack(
            [
                np.full(len(start_exons), "start_codon"),
                np.full(len(cds_exons), "CDS"),
                np.full(len(stop_exons), "stop_codon"),
            ]
        ).reshape(-1, 1)
        gtf_parts.append(np.hstack([coords_packed, exons_packed, features_packed]))
    gtf_lines = []
    for i, row in enumerate(df.iter_rows(named=True)):
        for start, stop, exon, feature in gtf_parts[i]:
            gtf_lines.append(
                row["seqname"]
                + "\tRiboTIE\t"
                + feature
                + "\t"
                + start
                + "\t"
                + stop
                + "\t.\t"
                + row["strand"]
                + '\t0\tgene_id "'
                + row["gene_id"]
                + '"; transcript_id "'
                + row["tr_id"]
                + '"; ORF_id "'
                + row["ORF_id"]
                + '"; model_output "'
                + f"{row['output']:.5}"
                + '"; orf_type "'
                + row["ORF_type"]
                + '"; exon_number "'
                + exon
                + '"; gene_name "'
                + row["gene_name"]
                + '"; transcript_biotype "'
                + row["tr_biotype"]
                + '"; tag "'
                + row["tr_tag"]
                + '"; transcript_support_level "'
                + row["tr_support_lvl"]
                + '";\n'
            )
    with open(f"{out_prefix}.gtf", "w") as f:
        for line in gtf_lines:
            f.write(line)
