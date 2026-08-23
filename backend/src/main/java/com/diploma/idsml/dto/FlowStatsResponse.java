package com.diploma.idsml.dto;

import java.util.List;

public record FlowStatsResponse(
        long totalFlows,
        List<AttackTypeCount> attackTypeCounts
) {
}
