package com.diploma.idsml.controller;

import com.diploma.idsml.dto.NetworkFlowResponse;
import com.diploma.idsml.service.NetworkFlowService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/flows")
public class NetworkFlowController {

    private final NetworkFlowService networkFlowService;

    public NetworkFlowController(NetworkFlowService networkFlowService) {
        this.networkFlowService = networkFlowService;
    }

    @GetMapping
    public List<NetworkFlowResponse> getAll() {
        return networkFlowService.getAll();
    }

    @GetMapping("/{id}")
    public NetworkFlowResponse getById(@PathVariable UUID id) {
        return networkFlowService.getById(id);
    }
}
