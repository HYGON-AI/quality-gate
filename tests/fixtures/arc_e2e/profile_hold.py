"""Keep real HCU kernels active during cancellation/Runner-loss windows."""
import json,time

def run(cards,node_rank,duration=420):
    if not cards:
        print('PROFILE_COMPUTE_READY '+json.dumps({'cards':0,'node_rank':node_rank,'active_gpu_hold':False}),flush=True)
        time.sleep(duration);return
    import torch
    assert torch.cuda.device_count()==cards
    torch.set_num_threads(1)
    tensors=[(torch.randn(512,512,device='cuda:'+str(i)),torch.randn(512,512,device='cuda:'+str(i))) for i in range(cards)]
    # Initialize every context and execute a kernel before announcing readiness.
    for i,(a,b) in enumerate(tensors):
        assert torch.isfinite(a@b).all().item();torch.cuda.synchronize(i)
    print('PROFILE_COMPUTE_READY '+json.dumps({'cards':cards,'node_rank':node_rank,'active_gpu_hold':True}),flush=True)
    until=time.monotonic()+duration
    while time.monotonic()<until:
        for i,(a,b) in enumerate(tensors):
            assert torch.isfinite(a@b).all().item();torch.cuda.synchronize(i)
