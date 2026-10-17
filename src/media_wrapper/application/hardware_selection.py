"""Explicit CPU/GPU/Auto planning from runtime evidence, never silent fallback."""
from dataclasses import replace

from media_wrapper.domain.capabilities import (
    GPU_ENCODERS,
    CapabilityReport,
    EncoderStatus,
)
from media_wrapper.domain.operations import OperationPlan


def select_hardware(plan: OperationPlan, report: CapabilityReport | None, mode: str,
                    preferred: str = 'auto') -> OperationPlan:
    if mode == 'CPU':
        return plan
    if mode not in {'GPU', 'Auto'}:
        raise ValueError('Unknown hardware mode')
    working = tuple(c for c in report.gpu if c.status == EncoderStatus.WORKING) if report else ()
    streams, decisions, device = [], [], None
    for selection in plan.streams:
        profile = selection.profile
        if profile.encoder not in {'libx264', 'libx265'}:
            streams.append(selection)
            continue
        codec = 'h264' if profile.encoder == 'libx264' else 'hevc'
        candidates = [c for c in working if GPU_ENCODERS[c.name] == codec and (preferred == 'auto' or c.name == preferred)]
        # This GPU slice supports default/bitrate control only; no portable CRF.
        if profile.crf is not None or plan.target_size_bytes is not None or plan.two_pass:
            candidates = []
        if not candidates:
            if mode == 'GPU':
                raise ValueError('No matching runtime-tested GPU encoder for these options. Test GPUs in Settings; use default/bitrate mode or choose CPU.')
            streams.append(selection)
            decisions.append(f'Auto selected CPU {profile.encoder}; no matching tested GPU/options')
            continue
        chosen = candidates[0]
        if chosen.name.endswith('_vaapi'):
            device = chosen.device
        streams.append(replace(selection, profile=replace(profile, encoder=chosen.name, preset=None)))
        decisions.append(f'{mode} selected {chosen.name} (runtime tested; rechecked before execution)')
    if mode == 'GPU' and not any(s.profile.encoder in GPU_ENCODERS for s in streams):
        raise ValueError('Select H.264 or H.265 video encoding to use GPU mode')
    return replace(plan, streams=tuple(streams), hardware_device=device, hardware_note='; '.join(decisions))


def cpu_retry_plan(plan: OperationPlan) -> OperationPlan:
    if not any(s.profile.encoder in GPU_ENCODERS for s in plan.streams):
        raise ValueError('This plan does not use a GPU encoder')
    streams = tuple(replace(s, profile=replace(s.profile,
                    encoder='libx264' if GPU_ENCODERS[s.profile.encoder] == 'h264' else 'libx265', preset='medium'))
                    if s.profile.encoder in GPU_ENCODERS else s for s in plan.streams)
    return replace(plan, streams=streams, output=replace(plan.output, temporary_path=None), hardware_device=None,
                   hardware_note='User explicitly requested CPU retry; previous attempt and partial output retained.')
