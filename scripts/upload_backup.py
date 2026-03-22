#!/usr/bin/env python3
"""
Upload backup file to S3 or FTP depending on environment variables.
Environment variables supported:
- S3_BUCKET (optional) -- upload to AWS S3; AWS credentials can be provided via env/AWS profile/instance role
- S3_KEY_PREFIX (optional) -- prefix/path in bucket (default: '')

OR
- FTP_HOST, FTP_USER, FTP_PASS, FTP_PATH (optional) -- upload to FTP server

Usage: python scripts/upload_backup.py /path/to/db-backup-xxxx.sql
"""
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def upload_s3(file_path, bucket, prefix=''):
    try:
        import boto3
    except Exception:
        logging.warning('boto3 not installed; trying aws cli if available')
        # fallback to aws cli
        import subprocess
        key = (prefix + '/' if prefix and not prefix.endswith('/') else prefix) + os.path.basename(file_path)
        cmd = ['aws', 's3', 'cp', file_path, f's3://{bucket}/{key}']
        logging.info('Running: %s', ' '.join(cmd))
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logging.error('aws cli upload failed: %s', res.stderr)
            return False
        logging.info('Uploaded to s3://%s/%s', bucket, key)
        return True

    s3 = boto3.client('s3')
    key = (prefix + '/' if prefix and not prefix.endswith('/') else prefix) + os.path.basename(file_path)
    logging.info('Uploading %s to s3://%s/%s', file_path, bucket, key)
    try:
        s3.upload_file(file_path, bucket, key)
        logging.info('Upload finished')
        return True
    except Exception as e:
        logging.error('S3 upload failed: %s', e)
        return False


def upload_ftp(file_path, host, user, password, path='/'):
    from ftplib import FTP
    logging.info('Uploading %s to FTP %s/%s', file_path, host, path)
    try:
        ftp = FTP(host)
        ftp.login(user, password)
        # ensure path exists - try CWD
        try:
            ftp.cwd(path)
        except Exception:
            # try to create path components
            parts = [p for p in path.split('/') if p]
            cur = '/'
            for p in parts:
                try:
                    ftp.mkd(p)
                except Exception:
                    pass
                ftp.cwd(p)
        with open(file_path, 'rb') as fh:
            ftp.storbinary('STOR ' + os.path.basename(file_path), fh)
        ftp.quit()
        logging.info('FTP upload finished')
        return True
    except Exception as e:
        logging.error('FTP upload failed: %s', e)
        return False


def main():
    if len(sys.argv) < 2:
        print('Usage: upload_backup.py <path-to-backup-file>')
        return 2
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print('File not found:', file_path)
        return 3

    # Try S3 first if configured
    s3_bucket = os.environ.get('S3_BUCKET')
    s3_prefix = os.environ.get('S3_KEY_PREFIX', '')
    ftp_host = os.environ.get('FTP_HOST')
    ftp_user = os.environ.get('FTP_USER')
    ftp_pass = os.environ.get('FTP_PASS')
    ftp_path = os.environ.get('FTP_PATH', '/')

    ok = True
    if s3_bucket:
        ok = upload_s3(file_path, s3_bucket, s3_prefix)
    elif ftp_host and ftp_user and ftp_pass:
        ok = upload_ftp(file_path, ftp_host, ftp_user, ftp_pass, ftp_path)
    else:
        logging.info('No upload destination configured (set S3_BUCKET or FTP_HOST). Skipping upload.')
        return 0

    return 0 if ok else 4

if __name__ == '__main__':
    sys.exit(main())
