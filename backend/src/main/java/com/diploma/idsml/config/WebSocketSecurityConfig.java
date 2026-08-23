package com.diploma.idsml.config;

import com.diploma.idsml.security.JwtService;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.messaging.simp.config.ChannelRegistration;

import java.util.List;

@Configuration
public class WebSocketSecurityConfig implements WebSocketMessageBrokerConfigurer {

    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtService jwtService;

    public WebSocketSecurityConfig(JwtService jwtService) {
        this.jwtService = jwtService;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);

                if (accessor == null || !StompCommand.CONNECT.equals(accessor.getCommand())) {
                    return message;
                }

                String header = accessor.getFirstNativeHeader("Authorization");
                if (header == null || !header.startsWith(BEARER_PREFIX)) {
                    throw new IllegalArgumentException("Mungon token-i i autorizimit.");
                }

                String token = header.substring(BEARER_PREFIX.length());
                accessor.setUser(jwtService.parse(token)
                        .map(claims -> new UsernamePasswordAuthenticationToken(
                                claims.getSubject(),
                                null,
                                List.of(new SimpleGrantedAuthority(
                                        "ROLE_" + claims.get("role", String.class)))
                        ))
                        .orElseThrow(() -> new IllegalArgumentException("Token i pavlefshem.")));

                return message;
            }
        });
    }
}
