package com.diploma.idsml.service;

import com.diploma.idsml.dto.DriftReportCreateRequest;
import com.diploma.idsml.dto.DriftReportResponse;
import com.diploma.idsml.dto.PageResponse;
import com.diploma.idsml.entity.DriftReport;
import com.diploma.idsml.entity.DriftStatus;
import com.diploma.idsml.repository.DriftReportRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class DriftReportService {

    private final DriftReportRepository driftReportRepository;

    public DriftReportService(DriftReportRepository driftReportRepository) {
        this.driftReportRepository = driftReportRepository;
    }

    @Transactional
    public DriftReportResponse record(DriftReportCreateRequest request) {
        Map<String, Object> details = new LinkedHashMap<>();
        if (request.features() != null) {
            details.put("features", request.features());
        }

        DriftReport report = DriftReport.builder()
                .status(request.status())
                .featureVersion(request.featureVersion())
                .observedFlows(request.observedFlows())
                .acceptedFlows(request.acceptedFlows())
                .rejectedFlows(request.rejectedFlows())
                .sampleSize(request.sampleSize())
                .invalidRate(request.invalidRate())
                .driftedFeatureCount(request.driftedFeatureCount())
                .driftedFraction(request.driftedFraction())
                .calibrationWindow(request.calibrationWindow())
                .reasons(request.reasons() != null ? request.reasons() : new ArrayList<>())
                .driftedFeatures(request.driftedFeatures() != null
                        ? request.driftedFeatures() : new ArrayList<>())
                .details(details)
                .generatedAt(request.generatedAt())
                .build();

        return toResponse(driftReportRepository.save(report));
    }

    public DriftReportResponse getLatest() {
        return driftReportRepository.findFirstByOrderByGeneratedAtDesc()
                .map(this::toResponse)
                .orElse(null);
    }

    public DriftStatus getCurrentStatus() {
        return driftReportRepository.findFirstByOrderByGeneratedAtDesc()
                .map(DriftReport::getStatus)
                .orElse(null);
    }

    public PageResponse<DriftReportResponse> history(Pageable pageable) {
        Page<DriftReport> page = driftReportRepository.findAllByOrderByGeneratedAtDesc(pageable);

        return new PageResponse<>(
                page.getContent().stream().map(this::toResponse).collect(Collectors.toList()),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages()
        );
    }

    private DriftReportResponse toResponse(DriftReport report) {
        return new DriftReportResponse(
                report.getId(),
                report.getStatus(),
                report.getFeatureVersion(),
                report.getObservedFlows(),
                report.getAcceptedFlows(),
                report.getRejectedFlows(),
                report.getSampleSize(),
                report.getInvalidRate(),
                report.getDriftedFeatureCount(),
                report.getDriftedFraction(),
                report.getCalibrationWindow(),
                List.copyOf(report.getReasons()),
                List.copyOf(report.getDriftedFeatures()),
                Map.copyOf(report.getDetails()),
                report.getGeneratedAt(),
                report.getCreatedAt()
        );
    }
}
