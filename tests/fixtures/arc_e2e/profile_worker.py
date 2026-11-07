"""One process per allocated HCU, all ranks exchange real identities and correctness tensors."""
import datetime,json,os,socket,time
from pathlib import Path
import torch
import torch.distributed as dist

rank=int(os.environ['RANK']);local=int(os.environ['LOCAL_RANK']);world=int(os.environ['WORLD_SIZE'])
cards=int(os.environ['CI_LOCAL_CARDS']);node_rank=int(os.environ['CI_NODE_RANK'])
assert os.getuid()==1001 and torch.cuda.device_count()==cards and rank==node_rank*cards+local
torch.set_num_threads(1);torch.cuda.set_device(local)
identity={'rank':rank,'local_rank':local,'node_rank':node_rank,'node':os.environ['NODE_NAME'],'ip':socket.gethostbyname(socket.gethostname())}
proof={'passed':False,'rank':rank,'world_size':world,'rounds':10}
for backend,device in [('gloo','cpu'),('nccl','cuda:'+str(local))]:
    dist.init_process_group(backend=backend,timeout=datetime.timedelta(seconds=75))
    raw=json.dumps(identity,sort_keys=True).encode();assert len(raw)<512
    ident=torch.zeros(512,dtype=torch.uint8,device=device);ident[:len(raw)]=torch.tensor(list(raw),dtype=torch.uint8,device=device)
    got=[torch.empty_like(ident) for _ in range(world)];dist.all_gather(got,ident)
    ids=[json.loads(bytes(x.cpu().tolist()).rstrip(b'\0')) for x in got]
    assert [x['rank'] for x in ids]==list(range(world))
    assert len({(x['node'],x['local_rank']) for x in ids})==world
    assert len({x['node'] for x in ids})==int(os.environ['CI_NNODES'])
    for n in range(10):
        x=torch.full((16384,),float(rank+n+1),device=device);dist.all_reduce(x)
        assert torch.equal(x,torch.full_like(x,float(world*n+world*(world+1)//2)))
        v=torch.tensor([rank,n],device=device);all_v=[torch.empty_like(v) for _ in range(world)];dist.all_gather(all_v,v)
        assert [a.cpu().tolist() for a in all_v]==[[i,n] for i in range(world)]
    dist.barrier();dist.destroy_process_group();proof[backend]=True;proof['identities']=ids
proof['passed']=True;Path('out/worker-'+str(rank)+'.json').write_text(json.dumps(proof))
print('PROFILE_RANK_PASS '+json.dumps(proof),flush=True)
