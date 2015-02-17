import os
import sys
from subprocess import Popen

from marmot.util.force_align import Aligner


def train_alignments(src_train, tg_train, tmp_dir, align_model='align_model'):
    cdec = os.environ['CDEC_HOME']
    if cdec == '':
        sys.stderr.write('No CDEC_HOME variable found. Please install cdec and/or set the variable\n')
        return ''
    if src_train == '' or tg_train == '':
        sys.stderr.write('No parallel corpus for training\n')
        return ''
    # join source and target files
    joint_name = tmp_dir + os.path.basename(src_train)+'_'+os.path.basename(tg_train)
    src_tg_file = open(joint_name, 'w')
    get_corp = Popen([cdec+'/corpus/paste-files.pl', src_train, tg_train], stdout=src_tg_file)
    get_corp.wait()
    src_tg_file.close()

    src_tg_clean = open(joint_name+'.clean', 'w')
    clean_corp = Popen([cdec+'/corpus/filter-length.pl', joint_name], stdout=src_tg_clean)
    clean_corp.wait()
    src_tg_clean.close()

    align_model_full = tmp_dir + '/' + align_model
    # train the alignment model
    fwd_align = open(align_model_full+'.fwd_align', 'w')
    rev_align = open(align_model_full+'.rev_align', 'w')
    fwd_err = open(align_model_full+'.fwd_err', 'w')
    rev_err = open(align_model_full+'.rev_err', 'w')

    fwd = Popen([cdec+'/word-aligner/fast_align', '-i'+joint_name+'.clean', '-d', '-v', '-o', '-p'+align_model_full+'.fwd_params'], stdout=fwd_align, stderr=fwd_err)
    rev = Popen([cdec+'/word-aligner/fast_align', '-i'+joint_name+'.clean', '-r', '-d', '-v', '-o', '-p'+align_model_full+'.rev_params'], stdout=rev_align, stderr=rev_err)
    fwd.wait()
    rev.wait()

    fwd_align.close()
    rev_align.close()
    fwd_err.close()
    rev_err.close()


def align_sentence(src_line, tg_line, align_model):
    # TODO: there is an error here if one or both fields are missing -- we cannot align a sentence without both src_line and tg_line
    # throw an error prompting the user to specify another dataset or context creator
    # if not src_line or not tg_line:

    cur_alignments = [[] for i in range(len(tg_line))]

    aligner = Aligner(align_model+'.fwd_params', align_model+'.fwd_err', align_model+'.rev_params', align_model+'.rev_err')
    align_str = aligner.align(' '.join(src_line)+u' ||| '+' '.join(tg_line))
    # parse the return value from the aligner
    for pair in align_str.split():
        pair = pair.split('-')
        cur_alignments[int(pair[1])].append(int(pair[0]))
    aligner.close()

    return cur_alignments
