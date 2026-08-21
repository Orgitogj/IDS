package com.diploma.idsml.controller;

import com.diploma.idsml.dto.NetworkFlowIngestRequest;
import com.diploma.idsml.dto.NetworkFlowResponse;
import com.diploma.idsml.service.NetworkFlowService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/alarms")
public class AlarmIngestController {

    private final NetworkFlowService networkFlowService;

    public AlarmIngestController(NetworkFlowService networkFlowService) {
        this.networkFlowService = networkFlowService;
    }

    @PostMapping("/ingest")
    public ResponseEntity<NetworkFlowResponse> ingest(@Valid @RequestBody NetworkFlowIngestRequest request) {
        NetworkFlowResponse response = networkFlowService.processFlowResult(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
