package com.diploma.idsml.controller;

import com.diploma.idsml.dto.UpdateUserEnabledRequest;
import com.diploma.idsml.dto.UserResponse;
import com.diploma.idsml.service.UserService;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/users")
@PreAuthorize("hasRole('ADMIN')")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping
    public List<UserResponse> list() {
        return userService.list();
    }

    @PatchMapping("/{id}/enabled")
    public UserResponse setEnabled(@PathVariable UUID id,
                                   @Valid @RequestBody UpdateUserEnabledRequest request,
                                   Authentication authentication) {
        return userService.setEnabled(id, request.enabled(), authentication.getName());
    }

    @PatchMapping("/{id}/unlock")
    public UserResponse unlock(@PathVariable UUID id) {
        return userService.unlock(id);
    }
}
