import torch
import torch.nn.functional as F
import torch.nn as nn
import numpy as np
import time
from tqdm import tqdm
from graphwriter import *
from utlis import *
from opts import *
import os
import sys

sys.path.append('./pycocoevalcap')
from pycocoevalcap.bleu.bleu import Bleu
from pycocoevalcap.rouge.rouge import Rouge
from pycocoevalcap.meteor.meteor import Meteor

def train_one_epoch(model, dataloader, optimizer, args, epoch):
    model.train()
    losses = []
    st_time = time.time()
    with tqdm(dataloader, desc='Train Ep '+str(epoch), mininterval=60) as tq:
        for batch in tq:
            pred = model(batch)
            nll_loss = F.nll_loss(pred.view(-1, pred.shape[-1]), batch['tgt_text'].view(-1), ignore_index=0)
            loss = nll_loss
            optimizer.zero_grad()
            loss.backward()
            #nn.utils.clip_grad_norm_(model.parameters(), args.clip)
            optimizer.step()
            loss = loss.item()
            if loss!=loss:
                raise ValueError('NaN appear')
            tq.set_postfix({'loss': loss}, refresh=False)
            losses.append(loss)
    print('Train Ep ', str(epoch), 'AVG Loss ', np.mean(losses), 'Steps ', len(losses), 'Time ', time.time()-st_time)
    torch.save(model, args.save_model)
         
def eval_it(model, dataloader, args, epoch):
    model.eval()
    losses = []
    st_time = time.time()
    with tqdm(dataloader, desc='Eval Ep '+str(epoch), mininterval=60) as tq:
        for batch in tq:
            with torch.no_grad():
                pred = model(batch)
                nll_loss = F.nll_loss(pred.view(-1, pred.shape[-1]), batch['tgt_text'].view(-1), ignore_index=0)
            loss = nll_loss
            loss = loss.item()
            tq.set_postfix({'loss': loss}, refresh=False)
            losses.append(loss)
    print('Eval Ep ', str(epoch), 'AVG Loss ', np.mean(losses), 'Steps ', len(losses), 'Time ', time.time()-st_time)

def test(model, dataloader, args):
    scorer = Bleu(4)
    m_scorer = Meteor()
    r_scorer = Rouge()
    hyp = []
    ref = []
    model.eval()
    gold_file = open('tmp_gold.txt', 'w')
    pred_file = open('tmp_pred.txt', 'w')
    with tqdm(dataloader, desc='Test ',  mininterval=1) as tq:
        for batch in tq:
            with torch.no_grad():
                beam_seq, beam_score = model(batch, beam_size=args.beam_size)
            h = write_txt(batch, batch['tgt_text'], gold_file, args)
            r = write_txt(batch, beam_seq, pred_file, args)
            hyp.extend(h)
            ref.extend(r)
    hyp = dict(zip(range(len(hyp)), hyp))
    ref = dict(zip(range(len(ref)), ref))
    print('BLEU INP', len(hyp), len(ref))
    print('BLEU', scorer.compute_score(ref, hyp)[0])
    print('METEOR', m_scorer.compute_score(ref, hyp)[0])
    print('ROUGE_L', r_scorer.compute_score(ref, hyp)[0])
    gold_file.close()
    pred_file.close()
    
def main(args):
    if os.path.exists(args.save_dataset):
        train_dataset, valid_dataset, test_dataset = pickle.load(open(args.save_dataset, 'rb'))
    else:
        train_dataset, valid_dataset, test_dataset = get_datasets(args.fnames, device=args.device, save=args.save_dataset)
    args = vocab_config(args, train_dataset.ent_vocab, train_dataset.rel_vocab, train_dataset.text_vocab)
    train_dataloader = torch.utils.data.DataLoader(train_dataset, batch_sampler = BucketSampler(train_dataset, batch_size=args.batch_size), \
                    collate_fn=train_dataset.batch_fn)
    valid_dataloader = torch.utils.data.DataLoader(valid_dataset, batch_size=args.batch_size, \
                    shuffle=False, collate_fn=train_dataset.batch_fn)
    test_dataloader = torch.utils.data.DataLoader(test_dataset, batch_size=args.batch_size, \
                    shuffle=False, collate_fn=train_dataset.batch_fn)

    model = GraphWriter(args)
    model.reset_parameter()
    model.to(args.device)
    if args.test:
        model = torch.load(args.save_model)
        model.args = args
        test(model, test_dataloader, args)
    else:
        #optimizer = torch.optim.SGD(model.parameters(), lr=args.lr, momentum=0.9)
        optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
        for epoch in range(args.epoch):
            train_one_epoch(model, train_dataloader, optimizer, args, epoch)
            eval_it(model, valid_dataloader, args, epoch)
            optimizer.param_groups[0]['lr'] *= args.lr_decay
    
if __name__ == '__main__':
    args = get_args()
    main(args)