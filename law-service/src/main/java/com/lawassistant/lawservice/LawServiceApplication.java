package com.lawassistant.lawservice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LawServiceApplication {

	static {
		System.setProperty("debug", "false");
	}

	public static void main(String[] args) {
		SpringApplication.run(LawServiceApplication.class, args);
	}

}
