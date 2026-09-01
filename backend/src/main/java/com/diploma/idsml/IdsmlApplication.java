package com.diploma.idsml;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class IdsmlApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdsmlApplication.class, args);
    }

}
