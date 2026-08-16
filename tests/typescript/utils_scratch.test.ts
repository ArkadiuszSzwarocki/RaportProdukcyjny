import { getExpiryStatus, getBlockInfo, normalizeLocationId } from './utils';

declare var describe: any;
declare var it: any;
declare var expect: any;

describe('Utils Logic Tests', () => {
    describe('getExpiryStatus', () => {
        const warningDays = 30;
        const criticalDays = 7;

        it('should return "expired" if date is in the past', () => {
            const pastDate = new Date();
            pastDate.setDate(pastDate.getDate() - 1);
            const palletData = { dataPrzydatnosci: pastDate.toISOString().split('T')[0] };
            
            expect(getExpiryStatus(palletData, warningDays, criticalDays)).toBe('expired');
        });

        it('should return "critical" if days left < criticalDays', () => {
            const nearDate = new Date();
            nearDate.setDate(nearDate.getDate() + 3);
            const palletData = { dataPrzydatnosci: nearDate.toISOString().split('T')[0] };

            expect(getExpiryStatus(palletData, warningDays, criticalDays)).toBe('critical');
        });

        it('should return "default" if date is far in the future', () => {
            const futureDate = new Date();
            futureDate.setDate(futureDate.getDate() + 100);
            const palletData = { dataPrzydatnosci: futureDate.toISOString().split('T')[0] };

            expect(getExpiryStatus(palletData, warningDays, criticalDays)).toBe('default');
        });
    });

    describe('getBlockInfo', () => {
        it('should mark item as blocked if manually blocked', () => {
            const item = {
                id: '1',
                isBlocked: true,
                blockReason: 'Manual block',
                expiryDate: '2099-01-01' // Future date
            };
            const result = getBlockInfo(item);
            expect(result.isBlocked).toBe(true);
            expect(result.reason).toContain('Manual block');
        });

        it('should mark item as blocked if expired (Automatic block)', () => {
            const item = {
                id: '1',
                isBlocked: false,
                expiryDate: '2000-01-01' // Past date
            };
            const result = getBlockInfo(item);
            expect(result.isBlocked).toBe(true);
            expect(result.type).toContain('A'); // Automatic
            expect(result.reason).toContain('Przeterminowana');
        });
    });

    describe('normalizeLocationId', () => {
        it('should normalize known aliases', () => {
            expect(normalizeLocationId('bfms01')).toBe('BF_MS01');
            expect(normalizeLocationId('BFMP01')).toBe('BF_MP01');
        });

        it('should return uppercase trim for standard inputs', () => {
            expect(normalizeLocationId('  ms01 ')).toBe('MS01');
        });
    });
});