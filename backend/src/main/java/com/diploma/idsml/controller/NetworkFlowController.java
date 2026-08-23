package com.diploma.idsml.controller;

import com.diploma.idsml.dto.FlowStatsResponse;
import com.diploma.idsml.dto.NetworkFlowResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.FlowLabel;
import com.diploma.idsml.service.NetworkFlowService;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/flows")
public class NetworkFlowController {

    private static final int MAX_PAGE_SIZE = 200;

    private final NetworkFlowService networkFlowService;

    public NetworkFlowController(NetworkFlowService networkFlowService) {
        this.networkFlowService = networkFlowService;
    }

    @GetMapping
    public PageResponse<NetworkFlowResponse> search(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size,
            @RequestParam(required = false) FlowLabel predictedLabel,
            @RequestParam(required = false) String search) {

        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), MAX_PAGE_SIZE);

        return networkFlowService.search(
                predictedLabel,
                search,
                PageRequest.of(safePage, safeSize, Sort.by(Sort.Direction.DESC, "createdAt"))
        );
    }

    @GetMapping("/stats")
    public FlowStatsResponse getStats() {
        return networkFlowService.getStats();
    }

    @GetMapping("/{id}")
    public NetworkFlowResponse getById(@PathVariable UUID id) {
        return networkFlowService.getById(id);
    }
}
