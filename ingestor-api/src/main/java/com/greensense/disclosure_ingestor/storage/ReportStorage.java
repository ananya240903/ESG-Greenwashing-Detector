package com.greensense.disclosure_ingestor.storage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.DigestOutputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.UUID;

/** Saves uploaded PDFs to the reports directory that the parser worker also mounts. */
@Component
public class ReportStorage {

    private static final byte[] PDF_MAGIC = "%PDF-".getBytes(StandardCharsets.US_ASCII);

    private final Path dir;

    public ReportStorage(@Value("${app.reports-dir}") String dir) throws IOException {
        this.dir = Path.of(dir).toAbsolutePath();
        Files.createDirectories(this.dir);
    }

    public record StoredFile(String key, String sha256) {
    }

    /** Streams the upload to disk, hashing it on the way. Rejects anything that is not a PDF. */
    public StoredFile store(MultipartFile file) {
        String key = UUID.randomUUID() + ".pdf";
        Path tmp = dir.resolve(key + ".part");
        try (InputStream in = file.getInputStream()) {
            byte[] head = in.readNBytes(PDF_MAGIC.length);
            if (!Arrays.equals(head, PDF_MAGIC)) {
                throw new IllegalArgumentException("File is not a PDF");
            }
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            try (OutputStream out = new DigestOutputStream(Files.newOutputStream(tmp), sha)) {
                out.write(head);
                in.transferTo(out);
            }
            Files.move(tmp, dir.resolve(key), StandardCopyOption.ATOMIC_MOVE);
            return new StoredFile(key, HexFormat.of().formatHex(sha.digest()));
        } catch (IOException e) {
            throw new UncheckedIOException("Could not store upload", e);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        } finally {
            try {
                Files.deleteIfExists(tmp);
            } catch (IOException ignored) {
                // best effort
            }
        }
    }

    public void delete(String key) {
        try {
            Files.deleteIfExists(dir.resolve(key));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
