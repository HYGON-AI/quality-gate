// Copyright (c) 2026 Hygon Information Technology Co., Ltd.
// SPDX-License-Identifier: Apache-2.0
#include <cstddef>
extern "C" void axpy(std::size_t n, double alpha, const double* x,
                     const double* y, double* output) {
    for (std::size_t i = 0; i < n; ++i) output[i] = alpha * x[i] + y[i];
}
