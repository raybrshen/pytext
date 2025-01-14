#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import unittest

import numpy as np
import torch
from pytext.models.representations.transformer import (
    Transformer,
    TransformerLayer,
    MultiheadSelfAttention,
)
from pytext.task.cuda_lowering import NVFasterTransformerEncoder


@unittest.skipIf(not torch.cuda.is_available(), "Skip when CUDA is not available")
class TestCUDALowering(unittest.TestCase):
    def testLoweringBaseTransformerToNVFastTransformer(self):
        V = 1000
        transformer = Transformer(vocab_size=V).cuda().eval().half()
        faster_transformer = NVFasterTransformerEncoder(transformer)

        for B in range(1, 32):
            for T in [0, 1, 7, 8, 16]:
                tokens = (
                    torch.randint(transformer.padding_idx + 1, V - 1, size=(B, T))
                    .cuda()
                    .long()
                )
                ref = transformer(tokens)
                fast = faster_transformer(tokens)
                for rref, ffast in zip(ref, fast):
                    torch.testing.assert_allclose(rref, ffast, atol=2e-2, rtol=2e-2)

    def testLoweringBaseTransformerToNVFastTransformerPadded(self):
        V = 1000
        transformer = Transformer(vocab_size=V).cuda().eval().half()
        faster_transformer = NVFasterTransformerEncoder(transformer)

        for B in range(1, 32):
            for max_T in [0, 1, 2, 6, 40, 127]:
                lengths = np.random.randint(low=0, high=max_T + 1, size=(B,))
                tokens = torch.zeros(B, max_T).cuda().long()
                for b in range(B):
                    length = lengths[b]
                    tokens[b, :length] = (
                        torch.randint(
                            transformer.padding_idx + 1, V - 1, size=(1, length)
                        )
                        .cuda()
                        .long()
                    )
                    tokens[b, length:] = transformer.padding_idx

                ref = transformer(tokens)
                fast = faster_transformer(tokens)
                for rref, ffast in zip(ref, fast):
                    for b in range(B):
                        length = lengths[b]
                        torch.testing.assert_allclose(
                            rref[:length, b], ffast[:length, b], atol=2e-2, rtol=2e-2
                        )

    def testLoweringLargeTransformerToNVFastTransformer(self):
        V = 1000
        L = 24
        D = 1024
        H = 16
        layers = [
            TransformerLayer(
                embedding_dim=D,
                attention=MultiheadSelfAttention(embed_dim=D, num_heads=H),
            )
            for _ in range(L)
        ]

        transformer = (
            Transformer(vocab_size=V, embedding_dim=D, layers=layers)
            .cuda()
            .eval()
            .half()
        )
        faster_transformer = NVFasterTransformerEncoder(transformer)
        for _ in range(10):
            B = np.random.randint(low=0, high=32)
            max_T = np.random.randint(low=0, high=32)
            lengths = np.random.randint(low=0, high=max_T + 1, size=(B,))
            tokens = torch.zeros(B, max_T).cuda().long()
            for b in range(B):
                length = lengths[b]
                tokens[b, :length] = (
                    torch.randint(transformer.padding_idx + 1, V - 1, size=(1, length))
                    .cuda()
                    .long()
                )
                tokens[b, length:] = transformer.padding_idx

                ref = transformer(tokens)
                fast = faster_transformer(tokens)
                for rref, ffast in zip(ref, fast):
                    for b in range(B):
                        length = lengths[b]
                        torch.testing.assert_allclose(
                            rref[:length, b], ffast[:length, b], atol=3e-2, rtol=2e-2
                        )

    def testLoweringTransformerToTracedNVFastTransformer(self):
        V = 1000
        transformer = Transformer(vocab_size=V).cuda().eval().half()
        faster_transformer = NVFasterTransformerEncoder(transformer)
        faster_transformer_jit = None

        for _ in range(10):
            B = np.random.randint(low=0, high=64)
            max_T = np.random.randint(low=0, high=64)
            lengths = np.random.randint(low=0, high=max_T + 1, size=(B,))
            tokens = torch.zeros(B, max_T).cuda().long()
            for b in range(B):
                length = lengths[b]
                tokens[b, :length] = (
                    torch.randint(transformer.padding_idx + 1, V - 1, size=(1, length))
                    .cuda()
                    .long()
                )
                tokens[b, length:] = transformer.padding_idx
                if not faster_transformer_jit:
                    faster_transformer_jit = torch.jit.trace(
                        faster_transformer, (tokens,)
                    )

                ref = transformer(tokens)
                fast = faster_transformer_jit(tokens)
                for rref, ffast in zip(ref, fast):
                    for b in range(B):
                        length = lengths[b]
                        torch.testing.assert_allclose(
                            rref[:length, b], ffast[:length, b], atol=2e-2, rtol=2e-2
                        )
