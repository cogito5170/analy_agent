bms_sil.so: ../firmware/src/bms.c ../firmware/include/bms.h
	gcc -shared -fPIC -I../firmware/include ../firmware/src/bms.c -o bms_sil.so

clean:
	rm -f bms_sil.so
